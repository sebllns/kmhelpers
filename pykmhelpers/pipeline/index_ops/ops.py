import logging
import os
import shutil
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import summarize_names
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.index_db import IndexDefinition, IndexDefinitionTools
from pykmhelpers.pipeline.index_ops.cluster import write_slurm
from pykmhelpers.pipeline.index_ops.executor import IndexExecutor, validate_definition
from pykmhelpers.pipeline.index_ops.layout import LayoutStore
from pykmhelpers.pipeline.index_ops.paths import BuildPaths, check_index_name
from pykmhelpers.pipeline.index_ops.plan_file import (
    MERGE,
    job_names,
    new_plan,
    write_plan,
)
from pykmhelpers.pipeline.index_ops.report import RunReport, indent_prefix
from pykmhelpers.pipeline.index_ops.samples import SampleResolver
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams, resolve_build_params
from pykmhelpers.pipeline.index_ops.sources import (
    SOURCES,
    DbCache,
    WorkPlan,
    detect_input,
)
from pykmhelpers.pipeline.index_ops.types import (
    ApplyInputType,
    ApplyMode,
    ApplyResult,
    ApplyStatus,
    IndexOpsConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class _Built:
    """Runs built for one definition, with what publishing them needs."""

    definition: IndexDefinition
    params: BuildParams
    runs: dict[str, int]


class IndexOps:
    """Plans k-mer index builds against the kmindex registry ``BUILD_DIR``.

    Loads an index definition or a span registry (see ``sources``), plans
    every selected definition as unregistered kmtricks runs, then the
    publication of each target: the runs of its parts, merged with its
    current version when it is already registered, become
    ``BUILD_DIR/<target>``. A definition that is not a part of a selected
    merge is its own target. Nothing is built: ``write_plan()`` writes the
    scripts of every task and ``plan.yaml``, which ``apply`` runs
    (``runner.PlanRunner``).

    Args:
        config: Runtime configuration governing paths, build parameters,
            filtering, and execution behaviour.  See ``IndexOpsConfig``.

    Attributes:
        config (IndexOpsConfig): The resolved configuration (``workdir`` is
            made absolute on construction).
        work_dir (str): ``BUILD_DIR``, the kmindex registry.
        asset_dir (str): ``<work_dir>/assets`` - one folder of scripts per session.
        log_dir (str): ``<work_dir>/logs`` - log file destination.
        timestamp (str): ``YYYYmmdd_HHMMSS`` string captured at construction.
    """

    def __init__(self, config: IndexOpsConfig) -> None:
        self._config = config
        self._config.workdir = os.path.realpath(config.workdir)
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Kept across runs: sample files are resolved relative to their definition file
        self._dbs = DbCache()
        self._script = ScriptRecorder(self.work_dir)
        self._paths: Optional[BuildPaths] = None
        self._input: Optional[str] = None
        self._inputs: list[str] = []
        self._limits: dict = {}
        # Tasks of the last run(), keyed by part name (see plan_file)
        self._tasks: dict[str, dict] = {}
        self._task_dirs: set[str] = set()

        logger.debug(f"Init {type(self).__name__}")
        logger.debug("workdir: " + self.work_dir)

        for d in (self.work_dir, self.log_dir, self.asset_dir):
            os.makedirs(d, exist_ok=True)

    # ---
    # PROPERTIES

    @property
    def config(self) -> IndexOpsConfig:
        return self._config

    @property
    def work_dir(self) -> str:
        return self.config.workdir

    @property
    def asset_dir(self) -> str:
        return os.path.join(self.work_dir, "assets")

    @property
    def log_dir(self) -> str:
        return os.path.join(self.work_dir, "logs")

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @property
    def paths(self) -> Optional[BuildPaths]:
        """Layout of the session of the last ``run()``."""
        return self._paths

    # ---
    # PUBLIC METHODS

    @property
    def tasks(self) -> dict[str, dict]:
        """Tasks planned by the last ``run()``, as written to ``plan.yaml``."""
        return self._tasks

    def write_plan(self, cluster: Optional[dict] = None) -> Optional[str]:
        """Write the scripts of the last ``run()`` and ``plan.yaml``; return its path.

        Under ``assets/<session>/``, one directory per task (``<shard>/``):
        one script per kmtricks run, ``merge.sh`` (publication and cleanup),
        their sample lists and merge inputs. With ``cluster`` (a loaded
        ``--cluster`` file), also ``slurm/``: the files submitting the jobs.
        """
        if self._paths is None or self._input is None:
            logger.warning("Nothing planned: no plan written")
            return None
        self._script.write(self._paths.assets)
        groups = set(self._script.groups)
        per_job = self.config.chunks_per_job
        for task in self._tasks.values():
            has_merge = ScriptRecorder.merge_group(task["dir"]) in groups
            if not has_merge:
                task.pop("merge", None)
            task["jobs"] = job_names(task["shard"], list(task["chunks"]), has_merge, per_job)
        options = {
            "limits": self._limits,
            "chunks_per_job": per_job,
            "skip_compression": self.config.kmindex_skip_compression,
            "keep_previous": self.config.keep_previous,
            "base_path": self.config.sample_rootpath,
        }
        plan = new_plan(
            self._input,
            self.work_dir,
            self._paths.session,
            self._inputs + ([cluster["source"]] if cluster else []),
            options,
            {name: _task_entry(t) for name, t in self._tasks.items()},
        )
        if cluster:
            plan["cluster"] = cluster
        write_plan(self._paths.plan, plan)
        if cluster:
            for path in write_slurm(plan, cluster, os.path.join(self._paths.assets, "slurm")):
                logger.debug(f"Written {path}")
            logger.info(
                f"Submit the jobs with: bash {os.path.join(self._paths.assets, 'slurm', 'submit.sh')}"
            )
        return self._paths.plan

    def run(
        self,
        path: str,
        mode: ApplyMode,
        fail_on_error: bool = False,
        report_path: Optional[str] = None,
    ) -> ApplyResult:
        """Plan an index definition or span registry file against the kmindex registry.

        Plans every selected definition, then the publication of every target.

        Args:
            path: Path to a YAML or JSON file containing either an
                ``IndexDefinition`` or a span registry.
            mode: ``PLAN``, or ``DRY_RUN`` to skip the sample file checks.
            report_path: Where to write the YAML report, updated as the run
                goes (after each definition and each publish) and at the end.
            fail_on_error: Abort this run on the first build or merge error
                instead of continuing and returning ``PARTIAL``.

        Returns:
            An ``ApplyResult`` with the overall status and a per-index details
            dict. Status is ``SUCCESS`` when all operations complete without
            error, ``PARTIAL`` when some fail (only when
            ``fail_on_error=False``), or ``FAILED`` when a fatal error occurs.
        """
        if mode.executes:
            raise ValueError("IndexOps only plans: `apply` runs the plan")
        path = os.path.realpath(path)
        self._script = ScriptRecorder(self.work_dir)
        self._paths = paths = BuildPaths.for_input(self.work_dir, path)
        self._input = path
        self._tasks = {}
        self._task_dirs = set()
        report = RunReport(path, mode, self.config, report_path)
        report.set_build_dir(self.work_dir, paths.assets)
        self._limits = report.result.details["limits"]
        samples: Optional[SampleResolver] = None
        try:
            samples = self._run(report, path, mode, fail_on_error)
        finally:
            report.close()
            layout = LayoutStore.next_to(path)
            self._inputs = (
                [path]
                + self._dbs.paths
                + ([layout.path] if layout.path else [])
                + (samples.files_read if samples else [])
            )
        return report.result

    # ---
    # PRIVATE METHODS

    def _run(
        self, report: RunReport, path: str, mode: ApplyMode, fail_on_error: bool
    ) -> Optional[SampleResolver]:
        paths = self._paths
        assert paths is not None
        idt = IndexDefinitionTools()

        input_type, data = detect_input(path, idt)
        report.set_input_type(input_type)
        if data is None or input_type is ApplyInputType.UNKNOWN:
            logger.error("Could not retrieve data type.")
            report.result.status = ApplyStatus.FAILED
            return None

        os.makedirs(paths.assets, exist_ok=True)
        builder = IndexBuilder(
            workdir=self.work_dir,
            registry_name=paths.registry,
            data_folder=paths.runs,
            log_folder=self.log_dir,
            assets_folder=os.path.relpath(paths.assets, self.work_dir),
        )
        try:
            plan = SOURCES[input_type](self.config, self._dbs).load(path, idt, data)
            targets = self._targets(plan)
            for name in targets:
                check_index_name(name)
        except Exception as e:
            Log.handle_exception(logger, e, f"Failed to load definition file '{path}'")
            report.result.status = ApplyStatus.FAILED
            return None

        layout = LayoutStore.next_to(path)
        executor = IndexExecutor(builder, self.config, self._script, paths)
        samples = SampleResolver(
            self.config.sample_rootpath, mode.checks_files, self._dbs
        )

        own_targets = {t for t, parts in targets.items() if parts == [t]}
        built: dict[str, _Built] = {}
        for i in plan.definitions:
            assert i.name  # WorkPlan only holds named definitions
            logger.info(f"► Processing index definition '{i.name}'...")
            if i.name in own_targets and executor.has_index(i.name):
                logger.info(f"  └── {i.name} found in registry: skip")
                report.record(i.name, ApplyStatus.NONE)
                continue
            try:
                target = plan.script_of(i.name)
                self._select_task(executor, target, target)
                b = self._build(report, executor, samples, i, layout, target)
                if b:
                    built[i.name] = b
            except Exception as e:
                msg = f"   Failed to plan index '{i.name}'"
                if report.fail(e, msg, i.name, fail_on_error):
                    return samples
            report.dump()

        for target, parts in targets.items():
            try:
                self._select_task(executor, plan.script_of(parts[0]), target)
                self._publish(report, executor, target, parts, built)
            except Exception as e:
                msg = f"Failed to plan the publication of '{target}'"
                if target in executor.publish_details:
                    report.record_merge(target, executor.publish_details[target])
                if report.fail(e, msg, target, fail_on_error):
                    return samples
            report.dump()

        report.finish()
        return samples

    def _select_task(self, executor: IndexExecutor, task_dir: str, target: str) -> None:
        """Record into ``assets/<session>/<task_dir>/``, emptied the first time."""
        assert self._paths is not None
        if task_dir not in self._task_dirs:
            self._task_dirs.add(task_dir)
            shutil.rmtree(self._paths.task(task_dir), ignore_errors=True)
        executor.set_task(task_dir, target)

    @staticmethod
    def _targets(plan: WorkPlan) -> dict[str, list[str]]:
        """Every index to publish, with the definitions it is made of.

        The merges of a span registry, plus every definition that is not a
        part of one of them (an index definition, or a part selected without
        its target), which is its own target.
        """
        targets = dict(plan.merges)
        in_merge = {p for parts in targets.values() for p in parts}
        for i in plan.definitions:
            if i.name and i.name not in in_merge:
                targets.setdefault(i.name, [i.name])
        return targets

    @staticmethod
    def _store_params(i: IndexDefinition, params: BuildParams) -> None:
        """Keep the size estimates of ``i`` in line with what is built."""
        i.partition_count = params.partitions

    def _resolve_params(
        self, i: IndexDefinition, sample_count: int, layout: LayoutStore
    ) -> BuildParams:
        params = resolve_build_params(i, sample_count, self.config, layout)
        # Keeps size estimates of i in line with what is built
        i.partition_count = params.partitions
        return params

    def _build(
        self,
        report: RunReport,
        executor: IndexExecutor,
        samples: SampleResolver,
        i: IndexDefinition,
        layout: LayoutStore,
        target: str,
    ) -> Optional[_Built]:
        """Build the runs of index ``i`` and record its outcome in ``report``."""
        # Partitions must be known before estimating the size
        params = self._resolve_params(i, i.sample_count, layout)
        size = i.get_stored_size()
        report.add_span_stats(i.span, i.sample_count, size.byte_count)
        logger.info(f"  └── Sample count: {i.sample_count}")
        logger.info(f"  └── Estimated build size: {size}")

        validate_definition(i)
        assert i.name is not None
        if not executor.claim(i.name):
            report.record(i.name, ApplyStatus.NONE)
            return None

        fof, issues = samples.build_fof(i)
        sample_count = fof.get_sample_count()
        if sample_count == 0:
            logger.warning(
                f"{indent_prefix(logger)}Skipping index '{i.name}' as no sample was added to it"
            )
            status = ApplyStatus.FAILED if issues else ApplyStatus.NONE
            report.record(i.name, status, issues=issues)
            return None

        # A part already in its target (rerun of a finished or interrupted session)
        published = executor.index_samples(target)
        overlap = published.intersection(fof.samples)
        if overlap and len(overlap) == sample_count:
            logger.info(
                f"  └── All samples of '{i.name}' are already in '{target}': skip"
            )
            report.record(i.name, ApplyStatus.NONE, issues=issues)
            return None
        if overlap:
            raise ValueError(
                f"{len(overlap)} of the {sample_count} samples of '{i.name}' are "
                f"already in '{target}' ({summarize_names(sorted(overlap))}): "
                f"a sample can only be added once"
            )

        # Samples may have been skipped since the estimate: resolve for the actual count
        if sample_count != i.sample_count:
            # i.partition_count now holds the first count: keep its source
            source = params.partitions_source
            params = self._resolve_params(i, sample_count, layout)
            params = replace(params, partitions_source=source)
        params = executor.align_with(target, params, i.name)
        self._store_params(i, params)
        report.record_params(i.name, i, params, sample_count)
        assert self._paths is not None
        report.record_script(i.name, self._paths.task(target))
        try:
            runs = executor.build(i, fof, params)
        finally:
            report.record_runs(
                i.name,
                {
                    r: executor.run_details[r]
                    for r in executor.run_names
                    if r in executor.run_details
                    and (r == i.name or r.startswith(f"{i.name}_chunk"))
                },
            )
        report.record(i.name, ApplyStatus.SUCCESS, issues=issues)
        self._tasks[i.name] = {
            "shard": target,
            "dir": target,
            "samples": sample_count,
            "span": i.span,
            "partitions": params.partitions,
            "minim_size": params.minim_size,
            "threads": params.threads,
            "chunks": {r: {"samples": n} for r, n in runs.items()},
        }
        return _Built(i, params, runs)

    def _publish(
        self,
        report: RunReport,
        executor: IndexExecutor,
        target: str,
        parts: list[str],
        built: dict[str, _Built],
    ) -> None:
        """Plan the publication of the runs of ``parts`` as ``target``.

        A folder ``BUILD_DIR/<target>`` left unregistered by an interrupted
        publish, with nothing new to add, is registered.
        """
        new = [built[p] for p in parts if p in built]
        failed = [
            p
            for p in parts
            if p not in built and report.result_of(p) == ApplyStatus.FAILED.value
        ]
        if failed:
            logger.warning(
                f"Cannot publish '{target}': {summarize_names(failed)} failed to plan"
            )
            if parts != [target]:
                report.fold_merge(target, parts)
            return

        registered = executor.has_index(target)
        # What the merge script assumes of the registry; checked by apply
        expects = {
            "registered": registered,
            "samples": len(executor.index_samples(target)) if registered else 0,
        }
        if not new:
            if executor.has_folder(target) and not registered:
                logger.info(f"► Registering '{target}' (publish interrupted)...")
                executor.register_folder(target, parts)
            self._record_publish(report, executor, target, parts, expects)
            return

        if len(new) > 1:
            raise ValueError(
                f"'{target}' gets {len(new)} parts in one session "
                f"({summarize_names([b.definition.name for b in new])}): one is expected"
            )
        logger.info(f"► Publishing '{target}'...")
        executor.publish(new[0].definition, target, new[0].runs, new[0].params)
        self._record_publish(report, executor, target, parts, expects)

    def _record_publish(
        self,
        report: RunReport,
        executor: IndexExecutor,
        target: str,
        parts: list[str],
        expects: dict,
    ) -> None:
        assert self._paths is not None
        details = dict(executor.publish_details.get(target, {}))
        if details:
            task_dir = executor.task_dir
            details["merge_script"] = os.path.join(
                self._paths.task(task_dir), f"{MERGE}.sh"
            )
            report.record_merge(target, details)
            part = next((p for p in parts if p in self._tasks), parts[0])
            task = self._tasks.setdefault(
                part,
                {"shard": target, "dir": task_dir, "samples": 0, "chunks": {}},
            )
            publish = details.get("publish", {})
            task["merge"] = {"script": f"{MERGE}.sh", "expects": expects, **publish}
        if parts != [target]:
            report.fold_merge(target, parts)


def _task_entry(task: dict) -> dict:
    """A task as written to ``plan.yaml``: its directory with a trailing slash."""
    entry = dict(task)
    entry["dir"] = task["dir"].rstrip("/") + "/"
    return entry
