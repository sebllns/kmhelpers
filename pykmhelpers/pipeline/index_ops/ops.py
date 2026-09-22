import logging
import os
from datetime import datetime
from typing import Optional

from pykmhelpers.core.log import Log
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.index_db import IndexDefinition, IndexDefinitionTools
from pykmhelpers.pipeline.index_ops.executor import IndexExecutor, validate_definition
from pykmhelpers.pipeline.index_ops.report import RunReport, indent_prefix
from pykmhelpers.pipeline.index_ops.samples import SampleResolver
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams, resolve_build_params
from pykmhelpers.pipeline.index_ops.sources import SOURCES, DbCache, detect_input
from pykmhelpers.pipeline.index_ops.types import (
    ApplyInputType,
    ApplyMode,
    ApplyResult,
    ApplyStatus,
    IndexOpsConfig,
)

logger = logging.getLogger(__name__)


class IndexOps:
    """Orchestrates k-mer index build and merge operations against a kmindex registry.

    Loads an index definition or a span registry (see ``sources``), builds
    the missing sub-indexes, merges partial indexes into their target and
    deletes the merged parts. In plan/dry-run modes, commands are only
    generated and can be exported as a shell script via ``write_script()``.

    Args:
        config: Runtime configuration governing paths, build parameters,
            filtering, and execution behaviour.  See ``IndexOpsConfig``.

    Attributes:
        config (IndexOpsConfig): The resolved configuration (paths are
            converted to absolute paths on construction).
        work_dir (str): Absolute path to the working directory.
        asset_dir (str): ``<work_dir>/assets`` - output location for generated
            shell scripts.
        log_dir (str): ``<work_dir>/logs`` - log file destination.
        kmindex_registry_dir (str): Path to the kmindex registry directory.
        kmindex_data_dir (str): Path to the folder that holds index data.
        timestamp (str): ``YYYYmmdd_HHMMSS`` string captured at construction.
    """

    def __init__(self, config: IndexOpsConfig) -> None:
        self._config = config
        self._config.workdir = os.path.realpath(config.workdir)
        self._config.index_data_folder = os.path.realpath(config.index_data_folder)
        self._config.registry_dir = os.path.realpath(config.registry_dir)
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Kept across runs: sample files are resolved relative to their definition file
        self._dbs = DbCache()
        self._script = ScriptRecorder(self.work_dir)

        logger.debug(f"Init {type(self).__name__}")
        logger.debug("workdir: " + self.work_dir)
        logger.debug("registry_dir: " + self.kmindex_registry_dir)
        logger.debug("asset_dir: " + self.asset_dir)
        logger.debug("data_dir: " + self.kmindex_data_dir)

        for d in (
            self.log_dir,
            self.asset_dir,
            self.kmindex_registry_dir,
            self.kmindex_data_dir,
        ):
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
    def kmindex_registry_dir(self) -> str:
        return self.config.registry_dir

    @property
    def kmindex_data_dir(self) -> str:
        return self.config.index_data_folder

    @property
    def timestamp(self) -> str:
        return self._timestamp

    # ---
    # PUBLIC METHODS

    def write_script(self) -> None:
        """Write the commands collected by the last ``run()`` to ``<asset_dir>/kmhelpers_apply.sh``.

        Any existing script is backed up with a ``.bak`` suffix.
        """
        self._script.write(self.asset_dir)

    def run(
        self, path: str, mode: ApplyMode, fail_on_error: bool = False
    ) -> ApplyResult:
        """Apply an index definition or span registry file to the kmindex registry.

        Builds every selected sub-index missing from the registry, then
        performs the merges declared by a span registry.

        Args:
            path: Path to a YAML or JSON file containing either an
                ``IndexDefinition`` or a span registry.
            mode: Execution mode - controls whether to dry-run, plan, or apply.
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
        report = RunReport(path, mode)
        idt = IndexDefinitionTools()

        input_type, data = detect_input(path, idt)
        report.result.input_type = input_type
        if data is None or input_type is ApplyInputType.UNKNOWN:
            logger.error("Could not retrieve data type.")
            report.result.status = ApplyStatus.FAILED
            return report.result

        builder = IndexBuilder(
            workdir=self.work_dir,
            registry_name=self.kmindex_registry_dir,
            data_folder=self.kmindex_data_dir,
            log_folder=self.log_dir,
        )
        try:
            plan = SOURCES[input_type](self.config, self._dbs).load(path, idt, data)
        except Exception as e:
            Log.handle_exception(logger, e, f"Failed to load definition file '{path}'")
            report.result.status = ApplyStatus.FAILED
            return report.result

        executor = IndexExecutor(builder, mode, self.config, self._script)
        samples = SampleResolver(
            self.config.sample_rootpath, mode.checks_files, self._dbs
        )

        for i in plan.definitions:
            assert i.name  # WorkPlan only holds named definitions
            logger.info(f"► Processing index definition '{i.name}'...")
            if executor.has_index(i.name):
                logger.info(f"  └── {i.name} found in registry: skip")
                report.record(i.name, ApplyStatus.NONE)
                continue
            try:
                self._build(report, executor, samples, i)
            except Exception as e:
                msg = f"   Failed to build index '{i.name}'"
                if report.fail(e, msg, i.name, fail_on_error):
                    return report.result

        for target, parts in plan.merges.items():
            try:
                self._merge(report, executor, target, parts)
            except Exception as e:
                msg = f"Failed to merge index '{target}'"
                if report.fail(e, msg, target, fail_on_error):
                    return report.result

        return report.finish()

    # ---
    # PRIVATE METHODS

    def _resolve_params(self, i: IndexDefinition, sample_count: int) -> BuildParams:
        params = resolve_build_params(i, sample_count, self.config)
        # Keeps size estimates of i in line with what is built
        i.partition_count = params.partitions
        return params

    def _build(
        self,
        report: RunReport,
        executor: IndexExecutor,
        samples: SampleResolver,
        i: IndexDefinition,
    ) -> None:
        """Build index ``i`` and record its outcome in ``report``."""
        # Partitions must be known before estimating the size
        params: Optional[BuildParams] = None
        if not i.partition_count:
            params = self._resolve_params(i, i.sample_count)
        size = i.get_stored_size()
        report.add_span_stats(i.span, i.sample_count, size.byte_count)
        logger.info(f"  └── Sample count: {i.sample_count}")
        logger.info(f"  └── Estimated build size: {size}")

        validate_definition(i)
        assert i.name is not None
        if not executor.claim(i.name):
            report.record(i.name, ApplyStatus.NONE)
            return

        fof, issues = samples.build_fof(i)
        sample_count = fof.get_sample_count()
        result = None
        if sample_count == 0:
            logger.warning(
                f"{indent_prefix(logger)}Skipping index '{i.name}' as no sample was added to it"
            )
        else:
            # Samples may have been skipped since the estimate: resolve for the actual count
            if params is None or sample_count != i.sample_count:
                params = self._resolve_params(i, sample_count)
            result = executor.build(i, fof, params)

        if not result:
            status = ApplyStatus.FAILED if issues else ApplyStatus.NONE
            report.record(i.name, status, issues=issues)
        elif not executor.executes or result.get("return_code", -1) == 0:
            report.record(i.name, ApplyStatus.SUCCESS, issues=issues)
        else:
            error = f"error_code={result['return_code']}"
            report.record(i.name, ApplyStatus.FAILED, error=error, issues=issues)

    def _merge(
        self, report: RunReport, executor: IndexExecutor, target: str, parts: list[str]
    ) -> None:
        """Merge ``parts`` into ``target``, record the outcome and delete the parts."""
        missing = executor.missing_parts(parts)
        if missing:
            logger.warning(
                f"Cannot merge '{target}' due to some sub-indexes missing: {missing}"
            )
            report.record(
                target, ApplyStatus.FAILED, error=f"Missing sub-indexes: {missing}"
            )
            return

        threads = self.config.kmindex_threads or os.cpu_count() or 1
        result = executor.merge(target, parts, threads)
        if not result or "command" not in result:
            raise Exception("Malformed result")
        report.fold_merge(target, parts)
        executor.finalize_merge(target, parts)
