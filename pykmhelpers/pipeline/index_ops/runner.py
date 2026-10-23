"""Run a plan: the scripts ``plan`` wrote, job by job (``kmhelpers apply``).

``PlanRunner`` loads ``BUILD_DIR/assets/<session>/plan.yaml``, refuses it when
its inputs changed, and runs the selected jobs (see ``plan_file``). Every step
is checked before it runs, so a job can be run again after an interruption:

- a task is **done** when its shard is registered and holds every sample of
  its chunks;
- a chunk is done when its task is, or when its kmtricks run is complete;
- before a merge, the registry must still be as ``plan`` saw it (``expects``),
  or as the merge itself leaves it when it was interrupted.
"""

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

from pykmhelpers.core.kmindex_paths import chunk_problems
from pykmhelpers.core.utils import matches_any, select_matching
from pykmhelpers.core.wrapper import Wrapper
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import MERGE, check_fresh, load_plan
from pykmhelpers.pipeline.index_ops.progress import ProgressDisplay
from pykmhelpers.pipeline.index_ops.report import RunReport, dir_bytes
from pykmhelpers.pipeline.index_ops.run_log import parse_kmtricks_log
from pykmhelpers.pipeline.index_ops.types import ApplyMode, ApplyResult, ApplyStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    name: str
    task: str  # part name, key of plan["tasks"]
    steps: tuple[str, ...]  # run names, and MERGE


class PlanRunner:
    """Runs the jobs of the plan of ``input_file`` in ``build_dir``."""

    def __init__(self, build_dir: str, input_file: str) -> None:
        input_file = os.path.realpath(input_file)
        self._paths = BuildPaths.for_input(build_dir, input_file)
        self._input = input_file
        self.plan = load_plan(self._paths.plan)
        check_fresh(self.plan, input_file)
        self._tasks: dict[str, dict] = self.plan.get("tasks") or {}
        self._shell = Wrapper("bash")
        # kmhelpers, kmindex and kmtricks of this installation come first
        bin_dir = os.path.dirname(sys.executable)
        if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    @property
    def plan_path(self) -> str:
        return self._paths.plan

    # ---
    # SELECTION

    def jobs(self, patterns: Optional[list[str]] = None) -> list[Job]:
        """Jobs of the plan, in order: every job, or those matching ``patterns``.

        A job is selected when a glob pattern matches its name (``<shard>``,
        ``<shard>_j<k>``, ``<shard>_merge``), its task (``<shard>_<session>``)
        or its shard: ``idx_g0`` selects every job of that shard,
        ``'idx_g0_j*'`` its chunk jobs, ``'*_merge'`` every merge.
        """
        jobs = [
            Job(job, task, tuple(steps))
            for task, entry in self._tasks.items()
            for job, steps in (entry.get("jobs") or {}).items()
        ]
        if not patterns:
            return jobs
        names = {
            j: (j.name, j.task, self._tasks[j.task]["shard"]) for j in jobs
        }
        # unmatched patterns: warned about, refused when nothing matches
        select_matching({n for ns in names.values() for n in ns}, patterns, "task")
        return [j for j in jobs if any(matches_any(n, patterns) for n in names[j])]

    def pending(self, jobs: Optional[list[Job]] = None) -> list[Job]:
        """Jobs with a step not done yet."""
        return [j for j in (self.jobs() if jobs is None else jobs) if not self.done(j)]

    def done(self, job: Job) -> bool:
        task = self._tasks[job.task]
        if self._task_done(task):
            return True
        if MERGE in job.steps:
            return False
        return all(self._chunk_complete(task, run) for run in job.steps)

    # ---
    # RUN

    def run(
        self,
        jobs: list[Job],
        fail_on_error: bool = False,
        show_progress: bool = False,
        report_path: Optional[str] = None,
    ) -> ApplyResult:
        """Run ``jobs`` in order; return the overall result.

        A failed step stops its task (its later steps are not run); the other
        tasks go on, unless ``fail_on_error``.
        """
        mode = ApplyMode.APPLY_SHOW_PROGRESS if show_progress else ApplyMode.APPLY
        report = RunReport(self._input, mode, None, report_path)
        report.set_build_dir(self._paths.build_dir, self._paths.assets)
        report.result.details["limits"] = (self.plan.get("options") or {}).get("limits", {})
        report.result.details["plan"] = self.plan_path
        failed_tasks: set[str] = set()
        try:
            for job in jobs:
                if job.task in failed_tasks:
                    logger.warning(f"Skipping job '{job.name}': its task failed")
                    continue
                logger.info(f"► Job '{job.name}'...")
                try:
                    self._run_job(report, job, show_progress)
                except Exception as e:
                    failed_tasks.add(job.task)
                    shard = self._tasks[job.task]["shard"]
                    if report.fail(e, f"Job '{job.name}' failed", shard, fail_on_error):
                        break
                report.dump()
            if report.result.status is not ApplyStatus.FAILED:
                status = report.finish().status
                if failed_tasks and status is ApplyStatus.SUCCESS:
                    report.result.status = ApplyStatus.PARTIAL
        finally:
            report.close()
        return report.result

    def _run_job(self, report: RunReport, job: Job, show_progress: bool) -> None:
        task = self._tasks[job.task]
        shard = task["shard"]
        runs: dict[str, dict] = {}
        merged = False
        try:
            for step in job.steps:
                if step == MERGE:
                    merged = self._run_merge(report, job.task, task, show_progress)
                else:
                    runs[step] = self._run_chunk(task, step, show_progress)
        finally:
            if runs:
                report.record_runs(shard, runs)
                entry = report.result.details["shards"].setdefault(shard, {})
                entry.setdefault("part", job.task)
                entry.setdefault(
                    "params",
                    {k: task.get(k) for k in ("partitions", "minim_size", "threads")},
                )
        if report.result_of(shard) in (None, ApplyStatus.NONE.value):
            built = merged or any(r["action"] == "built" for r in runs.values())
            report.record(shard, ApplyStatus.SUCCESS if built else ApplyStatus.NONE)

    def _run_chunk(self, task: dict, run: str, show_progress: bool) -> dict:
        info: dict = {"samples": task["chunks"][run].get("samples")}
        if self._task_done(task):
            logger.info(f"  └── '{run}': samples already published")
            return {**info, "action": "published"}
        if self._chunk_complete(task, run):
            logger.info(f"  └── Reusing complete run '{run}'")
            return {**info, "action": "reused"}
        log = os.path.join(self._paths.task_logs(task["dir"].rstrip("/")), f"{run}.log")
        logger.info(f"  └── Building '{run}'...")
        self._script(task, f"{run}.sh", log, run, show_progress)
        info.update(parse_kmtricks_log(log))
        info["log"] = log
        problems = chunk_problems(self._paths.run(run), task["partitions"])
        if problems:
            raise RuntimeError(f"Run '{run}' is incomplete: {', '.join(problems)}")
        return {**info, "action": "built"}

    def _run_merge(
        self, report: RunReport, part: str, task: dict, show_progress: bool
    ) -> bool:
        """Run the merge of ``task``; False when there was nothing to do."""
        shard = task["shard"]
        merge = task.get("merge") or {}
        details = {k: v for k, v in merge.items() if k not in ("script", "expects")}
        if self._task_done(task):
            logger.info(f"  └── '{shard}' already holds the samples of '{part}'")
            report.record_merge(shard, {"publish": {**details, "action": "done"}})
            return False
        missing = [r for r in task["chunks"] if not self._chunk_complete(task, r)]
        if missing:
            jobs = [
                j for j, steps in task["jobs"].items() if set(steps) & set(missing)
            ]
            raise RuntimeError(
                f"Cannot merge '{shard}': runs not built ({', '.join(missing)}); "
                f"run job(s) {', '.join(jobs)} first"
            )
        self._check_expects(shard, merge.get("expects") or {})

        log = os.path.join(self._paths.task_logs(task["dir"].rstrip("/")), "merge.log")
        logger.info(f"  └── Publishing '{shard}'...")
        start = time.monotonic()
        self._script(task, merge.get("script", f"{MERGE}.sh"), log, shard, show_progress)
        details["duration_s"] = round(time.monotonic() - start, 1)
        details["log"] = log
        report.record_merge(
            shard, {"publish": details, "disk_bytes": dir_bytes(self._paths.shard(shard))}
        )
        report.record(shard, ApplyStatus.SUCCESS)
        if not self._task_done(task):
            raise RuntimeError(f"'{shard}' does not hold the samples of '{part}'")
        return True

    def _script(
        self, task: dict, script: str, log: str, name: str, show_progress: bool
    ) -> None:
        path = os.path.join(self._paths.task(task["dir"].rstrip("/")), script)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        display = ProgressDisplay(name) if show_progress else None
        if display:
            display.__enter__()
        try:
            result = self._shell._monitor_cmd(
                ["bash", path], log_file=log, log_errors_only=False
            )
        finally:
            if display:
                display.__exit__(None, None, None)
                print()
        code = (result or {}).get("return_code", -1)
        if code != 0:
            stderr = str((result or {}).get("stderr") or "").strip().splitlines()
            tail = "\n".join(stderr[-10:])
            raise RuntimeError(f"{script} failed (exit {code}), log: {log}\n{tail}")

    # ---
    # STATE

    def _check_expects(self, shard: str, expects: dict) -> None:
        """Refuse a registry changed since ``plan`` in a way this merge does not explain."""
        registered = self._registered(shard)
        if not registered:
            # new shard, or a swap of this merge interrupted after the unregister
            return
        if not expects.get("registered"):
            raise ValueError(
                f"'{shard}' was registered since the plan was made: run `kmhelpers plan` again"
            )
        held = len(self._published(shard))
        if held != expects.get("samples"):
            raise ValueError(
                f"'{shard}' holds {held} samples, the plan expects {expects.get('samples')}: "
                "run `kmhelpers plan` again"
            )

    def _registered(self, shard: str) -> bool:
        path = os.path.join(self._paths.registry, "index.json")
        try:
            with open(path) as f:
                return shard in (json.load(f).get("index") or {})
        except (OSError, ValueError):
            return False

    def _published(self, shard: str) -> set[str]:
        return _fof_names(os.path.join(self._paths.shard(shard), "kmtricks.fof"))

    def _task_samples(self, task: dict) -> set[str]:
        directory = self._paths.task(task["dir"].rstrip("/"))
        names: set[str] = set()
        for run in task["chunks"]:
            names |= _fof_names(os.path.join(directory, f"{run}.fof"))
        return names

    def _task_done(self, task: dict) -> bool:
        if not self._registered(task["shard"]):
            return False
        return self._task_samples(task) <= self._published(task["shard"])

    def _chunk_complete(self, task: dict, run: str) -> bool:
        return not chunk_problems(self._paths.run(run), task["partitions"])


def _fof_names(path: str) -> set[str]:
    try:
        with open(path) as f:
            return {
                line.split(":", 1)[0].strip() for line in f if line.split(":", 1)[0].strip()
            }
    except OSError:
        return set()


def describe(job: Job) -> str:
    steps = [s for s in job.steps if s != MERGE]
    parts = [f"{len(steps)} run(s)"] if steps else []
    if MERGE in job.steps:
        parts.append("merge")
    return f"{job.name}: {' + '.join(parts) or 'nothing'}"

