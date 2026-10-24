"""Run a plan: the scripts ``plan`` wrote, job by job (``kmhelpers apply``).

``PlanRunner`` loads ``BUILD_DIR/assets/<session>/plan.yaml``, refuses it when
its inputs changed, and runs the selected jobs (see ``plan_file``). Every step
is checked before it runs, so a job can be run again after an interruption:

- a task is **done** when its shard is registered and holds every sample of
  its chunks;
- a chunk is done when its task is, or when its kmtricks run is complete;
- before publishing, the registry must still be as ``plan`` saw it (``expects``),
  or as the publish step itself leaves it when it was interrupted.

Each step it runs is recorded in a state file, and ``progress.yaml`` is
rewritten after each one (see ``status``).
"""

import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

from pykmhelpers.core.kmindex_paths import chunk_problems
from pykmhelpers.core.utils import matches_any, select_matching
from pykmhelpers.core.wrapper import Wrapper
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import PUBLISH, check_fresh, load_plan
from pykmhelpers.pipeline.index_ops.progress import ShardDisplay
from pykmhelpers.pipeline.index_ops.report import RunReport, dir_bytes
from pykmhelpers.pipeline.index_ops.run_log import parse_kmtricks_log
from pykmhelpers.pipeline.index_ops.status import (
    CANCELLED,
    FAILED,
    RUNNING,
    SUCCESS,
    BuildState,
)
from pykmhelpers.pipeline.index_ops.types import ApplyMode, ApplyResult, ApplyStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    name: str
    task: str  # part name, key of plan["tasks"]
    steps: tuple[str, ...]  # run names, and PUBLISH


class PlanRunner:
    """Runs the jobs of the plan of ``input_file`` in ``build_dir``."""

    def __init__(self, build_dir: str, input_file: str) -> None:
        input_file = os.path.realpath(input_file)
        self._paths = BuildPaths.for_input(build_dir, input_file)
        self._input = input_file
        self.plan = load_plan(self._paths.plan)
        check_fresh(self.plan, input_file)
        self._tasks: dict[str, dict] = self.plan.get("tasks") or {}
        self.state = BuildState(self.plan, self._paths)
        self._shell = Wrapper("bash")
        self._current: Optional[tuple[dict, str]] = None  # step running now
        self._display: Optional[ShardDisplay] = None
        # kmhelpers, kmindex and kmtricks of this installation come first
        bin_dir = os.path.dirname(sys.executable)
        if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    @property
    def plan_path(self) -> str:
        return self._paths.plan

    def ram_budget(self) -> Optional[int]:
        """The RAM limit the plan was sized for (bytes), if it has one."""
        ram = ((self.plan.get("options") or {}).get("limits") or {}).get("ram_bytes")
        return int(ram) if ram else None

    # ---
    # SELECTION

    def jobs(self, patterns: Optional[list[str]] = None) -> list[Job]:
        """Jobs of the plan, in order: every job, or those matching ``patterns``.

        A job is selected when a glob pattern matches its name (``<shard>``,
        ``<shard>_j<k>``, ``<shard>_publish``), its task (``<shard>_<session>``)
        or its shard: ``idx_g0`` selects every job of that shard,
        ``'idx_g0_j*'`` its chunk jobs, ``'*_publish'`` every publish job.
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
        if PUBLISH in job.steps:
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
        on_task_end: Optional[Callable[[str, str], None]] = None,
        detailed: bool = False,
    ) -> ApplyResult:
        """Run ``jobs`` in order; return the overall result.

        A failed step stops its task (its later steps are not run); the other
        tasks go on, unless ``fail_on_error``. ``on_task_end(shard, status)``
        is called when a task ends here: its last step done, or a step failed.
        ``detailed`` (with ``show_progress``): the running step in detail, its
        RAM against the plan's RAM limit.
        """
        mode = ApplyMode.APPLY_SHOW_PROGRESS if show_progress else ApplyMode.APPLY
        report = RunReport(self._input, mode, None, report_path)
        report.set_build_dir(self._paths.build_dir, self._paths.assets)
        report.result.details["limits"] = (self.plan.get("options") or {}).get("limits", {})
        report.result.details["plan"] = self.plan_path
        failed_tasks: set[str] = set()
        previous = self._on_sigterm()
        if show_progress:
            tasks = list(dict.fromkeys(j.task for j in jobs))
            self._display = ShardDisplay(self.state, tasks, detailed=detailed).start()
        try:
            for job in jobs:
                if job.task in failed_tasks:
                    logger.warning(f"Skipping job '{job.name}': its task failed")
                    continue
                logger.info(f"► Job '{job.name}'...")
                shard = self._tasks[job.task]["shard"]
                try:
                    self._run_job(report, job, show_progress)
                except Exception as e:
                    failed_tasks.add(job.task)
                    if on_task_end:
                        on_task_end(shard, FAILED)
                    if report.fail(e, f"Job '{job.name}' failed", shard, fail_on_error):
                        break
                else:
                    if on_task_end and self._ends_task(job):
                        on_task_end(shard, SUCCESS)
                report.dump()
            if report.result.status is not ApplyStatus.FAILED:
                status = report.finish().status
                if failed_tasks and status is ApplyStatus.SUCCESS:
                    report.result.status = ApplyStatus.PARTIAL
        finally:
            signal.signal(signal.SIGTERM, previous)
            if self._display:
                self._display.close()
                self._display = None
            report.close()
        return report.result

    def _ends_task(self, job: Job) -> bool:
        """``job`` is the last job of its task (its publish job, or its only job)."""
        jobs = list(self._tasks[job.task].get("jobs") or {})
        return bool(jobs) and jobs[-1] == job.name

    def _on_sigterm(self):
        """On SIGTERM (scancel, time limit), record the running step as
        CANCELLED, then let the previous handler (or exit 143) end the process."""
        previous = signal.getsignal(signal.SIGTERM)

        def handler(sig, frame):
            if self._current:
                task, step = self._current
                self._record(task, step, CANCELLED, error="SIGTERM")
            if callable(previous):
                previous(sig, frame)
            sys.exit(128 + sig)

        signal.signal(signal.SIGTERM, handler)
        return previous

    def _record(self, task: dict, step: str, status: str, **fields) -> None:
        """Record the state of a step, then refresh progress.yaml; never fails a run."""
        try:
            self.state.write_state(task, step, status, **fields)
            self.state.write_progress()
        except Exception as e:
            logger.warning(f"Could not record the state of '{step}': {e}")
        if self._display:
            self._display.update()

    def _step(self, task: dict, step: str, log: str, run) -> None:
        """Run ``run()`` as step ``step`` of ``task``, recording its state."""
        self._current = (task, step)
        self._record(task, step, RUNNING, log=log)
        try:
            run()
        except Exception as e:
            first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            self._record(task, step, FAILED, log=log, error=first)
            raise
        finally:
            self._current = None
        self._record(task, step, SUCCESS, log=log)

    def _run_job(self, report: RunReport, job: Job, show_progress: bool) -> None:
        task = self._tasks[job.task]
        shard = task["shard"]
        runs: dict[str, dict] = {}
        published = False
        try:
            for step in job.steps:
                if step == PUBLISH:
                    published = self._run_publish(report, job.task, task, show_progress)
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
            built = published or any(r["action"] == "built" for r in runs.values())
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

        def build() -> None:
            self._script(task, f"{run}.sh", log, run, show_progress)
            problems = chunk_problems(self._paths.run(run), task["partitions"])
            if problems:
                raise RuntimeError(f"Run '{run}' is incomplete: {', '.join(problems)}")

        try:
            self._step(task, run, log, build)
        finally:
            info.update(parse_kmtricks_log(log))
            info["log"] = log
        return {**info, "action": "built"}

    def _run_publish(
        self, report: RunReport, part: str, task: dict, show_progress: bool
    ) -> bool:
        """Publish ``task``; False when there was nothing to do."""
        shard = task["shard"]
        publish = task.get("publish") or {}
        details = {k: v for k, v in publish.items() if k not in ("script", "expects")}
        if self._task_done(task):
            logger.info(f"  └── '{shard}' already holds the samples of '{part}'")
            report.record_publish(shard, {"publish": {**details, "action": "done"}})
            return False
        missing = [r for r in task["chunks"] if not self._chunk_complete(task, r)]
        if missing:
            jobs = [
                j for j, steps in task["jobs"].items() if set(steps) & set(missing)
            ]
            raise RuntimeError(
                f"Cannot publish '{shard}': runs not built ({', '.join(missing)}); "
                f"run job(s) {', '.join(jobs)} first"
            )
        self._check_expects(shard, publish.get("expects") or {})

        log = os.path.join(self._paths.task_logs(task["dir"].rstrip("/")), "publish.log")
        logger.info(f"  └── Publishing '{shard}'...")
        start = time.monotonic()

        def run_script() -> None:
            self._script(task, publish.get("script", f"{PUBLISH}.sh"), log, PUBLISH, show_progress)
            if not self._task_done(task):
                raise RuntimeError(f"'{shard}' does not hold the samples of '{part}'")

        self._step(task, PUBLISH, log, run_script)
        details["duration_s"] = round(time.monotonic() - start, 1)
        details["log"] = log
        report.record_publish(
            shard, {"publish": details, "disk_bytes": dir_bytes(self._paths.shard(shard))}
        )
        report.record(shard, ApplyStatus.SUCCESS)
        return True

    def _script(
        self, task: dict, script: str, log: str, step: str, show_progress: bool
    ) -> None:
        path = os.path.join(self._paths.task(task["dir"].rstrip("/")), script)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        on_sample = None
        if show_progress and self._display and self._display.detailed:
            display, shard, budget = self._display, task["shard"], self.ram_budget()

            def on_sample(rss: int) -> None:
                display.set_ram(shard, step, rss, budget)

        result = self._shell._monitor_cmd(
            ["bash", path], log_file=log, log_errors_only=False, on_sample=on_sample
        )
        code = (result or {}).get("return_code", -1)
        if code != 0:
            stderr = [ln for ln in str((result or {}).get("stderr") or "").splitlines() if ln.strip()]
            last = f": {stderr[-1].strip()}" if stderr else ""
            tail = "\n".join(stderr[-10:])
            # first line: what the state file and progress.yaml show
            raise RuntimeError(f"{script} failed (exit {code}){last}\nlog: {log}\n{tail}")

    # ---
    # STATE

    def _check_expects(self, shard: str, expects: dict) -> None:
        """Refuse a registry changed since ``plan`` in a way this publish step does not explain."""
        registered = self._registered(shard)
        if not registered:
            # new shard, or a swap of this publish step interrupted after the unregister
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
        return self.state.registered(shard)

    def _published(self, shard: str) -> set[str]:
        return self.state.published(shard)

    def _task_done(self, task: dict) -> bool:
        return self.state.task_done(task)

    def _chunk_complete(self, task: dict, run: str) -> bool:
        return self.state.chunk_complete(task, run)


def describe(job: Job) -> str:
    steps = [s for s in job.steps if s != PUBLISH]
    parts = [f"{len(steps)} run(s)"] if steps else []
    if PUBLISH in job.steps:
        parts.append("publish")
    return f"{job.name}: {' + '.join(parts) or 'nothing'}"

