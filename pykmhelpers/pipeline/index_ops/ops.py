import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional

from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import select_matching, summarize_names
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.index_db import IndexDefinition, IndexDefinitionTools
from pykmhelpers.pipeline.index_ops.executor import IndexExecutor, validate_definition
from pykmhelpers.pipeline.index_ops.layout import LayoutStore
from pykmhelpers.pipeline.index_ops.paths import BuildPaths, check_index_name
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
    """Orchestrates k-mer index builds against the kmindex registry ``BUILD_DIR``.

    Loads an index definition or a span registry (see ``sources``), builds
    every selected definition as unregistered kmtricks runs, then publishes
    each target: the runs of its parts, merged with its current version when
    it is already registered, become ``BUILD_DIR/<target>``. A definition
    that is not a part of a selected merge is its own target. In plan/dry-run
    modes, commands are only generated and can be exported as shell scripts
    via ``write_script()``.

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

    def write_script(self) -> None:
        """Write the commands collected by the last ``run()`` to ``assets/<session>/``.

        One script per group of parts (``<shard>.sh``: builds, then
        ``<shard>_merge.sh``: publication and cleanup), plus
        ``kmhelpers_apply.sh`` running them in order. Existing files are
        backed up with a ``.bak`` suffix.
        """
        if self._paths is None:
            logger.warning("Nothing planned: no script written")
            return
        self._script.write(self._paths.assets)

    def run(
        self,
        path: str,
        mode: ApplyMode,
        fail_on_error: bool = False,
        report_path: Optional[str] = None,
    ) -> ApplyResult:
        """Apply an index definition or span registry file to the kmindex registry.

        Builds every selected definition, then publishes every target.

        Args:
            path: Path to a YAML or JSON file containing either an
                ``IndexDefinition`` or a span registry.
            mode: Execution mode - controls whether to dry-run, plan, or apply.
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
        path = os.path.realpath(path)
        self._script = ScriptRecorder(self.work_dir)
        self._paths = paths = BuildPaths.for_input(self.work_dir, path)
        report = RunReport(path, mode, self.config, report_path)
        report.set_build_dir(self.work_dir, paths.assets)
        try:
            self._run(report, path, mode, fail_on_error)
        finally:
            report.close()
        return report.result

    # ---
    # PRIVATE METHODS

    def _run(
        self, report: RunReport, path: str, mode: ApplyMode, fail_on_error: bool
    ) -> ApplyResult:
        paths = self._paths
        assert paths is not None
        idt = IndexDefinitionTools()

        input_type, data = detect_input(path, idt)
        report.set_input_type(input_type)
        if data is None or input_type is ApplyInputType.UNKNOWN:
            logger.error("Could not retrieve data type.")
            report.result.status = ApplyStatus.FAILED
            return report.result

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
            return report.result

        layout = LayoutStore.next_to(path)
        executor = IndexExecutor(builder, mode, self.config, self._script, paths)
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
                self._script.select(plan.script_of(i.name))
                b = self._build(
                    report, executor, samples, i, layout, plan.script_of(i.name)
                )
                if b:
                    built[i.name] = b
            except Exception as e:
                msg = f"   Failed to build index '{i.name}'"
                if report.fail(e, msg, i.name, fail_on_error):
                    return report.result
            report.dump()

        if self.config.filter_runs:
            # --run builds runs only: a later run with --shard alone merges them
            try:
                select_matching(
                    executor.run_names, self.config.filter_runs, "kmtricks run"
                )
            except ValueError as e:
                report.fail(e, "Invalid --run", None, True)
                return report.result
            logger.info("Runs built, nothing merged (--run)")
            return report.finish()

        for target, parts in targets.items():
            try:
                self._publish(report, executor, plan, target, parts, built)
            except Exception as e:
                msg = f"Failed to publish index '{target}'"
                if target in executor.publish_details:
                    report.record_merge(target, executor.publish_details[target])
                if report.fail(e, msg, target, fail_on_error):
                    return report.result
            report.dump()

        return report.finish()

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
        report.record_script(i.name, os.path.join(self._paths.assets, f"{target}.sh"))
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
        return _Built(i, params, runs)

    def _publish(
        self,
        report: RunReport,
        executor: IndexExecutor,
        plan: WorkPlan,
        target: str,
        parts: list[str],
        built: dict[str, _Built],
    ) -> None:
        """Publish the runs of ``parts`` as ``target`` and record the outcome.

        Parts that are indexes of ``BUILD_DIR`` (left by an older kmhelpers,
        which registered parts before merging them) are merged in as they are.
        A folder ``BUILD_DIR/<target>`` left unregistered by an interrupted
        publish, with nothing new to add, is registered.
        """
        new = [built[p] for p in parts if p in built]
        absorbed = [
            p
            for p in parts
            if p != target and (executor.has_index(p) or executor.has_folder(p))
        ]
        failed = [
            p
            for p in parts
            if p not in built
            and p not in absorbed
            and report.result_of(p) == ApplyStatus.FAILED.value
        ]
        if failed:
            logger.warning(
                f"Cannot publish '{target}': {summarize_names(failed)} failed to build"
            )
            if parts != [target]:
                report.fold_merge(target, parts)
            return
        if not new:
            if executor.has_folder(target) and not executor.has_index(target):
                logger.info(f"► Registering '{target}' (publish interrupted)...")
                self._script.select(plan.script_of(parts[0]))
                executor.register_folder(target, parts)
            self._record_publish(report, executor, plan, target, parts)
            return

        logger.info(f"► Publishing '{target}'...")
        runs = {name: n for b in new for name, n in b.runs.items()}
        self._script.select(plan.script_of(parts[0]))
        executor.publish(new[0].definition, target, runs, new[0].params, absorbed)
        self._record_publish(report, executor, plan, target, parts)

    def _record_publish(
        self,
        report: RunReport,
        executor: IndexExecutor,
        plan: WorkPlan,
        target: str,
        parts: list[str],
    ) -> None:
        assert self._paths is not None
        details = dict(executor.publish_details.get(target, {}))
        if details:
            group = ScriptRecorder.merge_group(plan.script_of(parts[0]))
            details["merge_script"] = os.path.join(self._paths.assets, f"{group}.sh")
            report.record_merge(target, details)
        if parts != [target]:
            report.fold_merge(target, parts)
