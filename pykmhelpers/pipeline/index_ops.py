import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import sleep
from typing import Optional

from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.log import Log
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import (
    IndexDB,
    IndexDefinition,
    IndexDefinitionTools,
    Sample,
    SerializedDataType,
)

logger = logging.getLogger(__name__)


class ApplyMode(int, Enum):
    DRY_RUN = 0
    PLAN = 1
    APPLY = 2
    APPLY_SHOW_PROGRESS = 3


class ApplyStatus(str, Enum):
    """Status of an apply operation."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NONE = "NONE"


class ApplyInputType(str, Enum):
    """Type of the input file passed to an apply operation.

    Values:
        UNKNOWN: File type could not be determined.
        SPAN_REGISTRY: Input is a span registry file describing how partial
            indexes should be merged.
        INDEX_DEFINITION: Input is an index definition file describing one or
            more sub-indexes to build.
        NONE: No input file has been inspected yet.
    """

    UNKNOWN = "unknown"
    SPAN_REGISTRY = "span registry"
    INDEX_DEFINITION = "index definition"
    NONE = "none"


@dataclass
class ApplyResult:
    """Result of an apply operation.

    Attributes:
        status: Overall outcome of the operation.
        input_type: Detected type of the input file that was processed.
        details: Per-index outcome strings keyed by index name, plus an
            ``"input_file"`` entry with the resolved path of the source file.
    """

    status: ApplyStatus = ApplyStatus.NONE
    input_type: ApplyInputType = ApplyInputType.NONE
    mode: ApplyMode = ApplyMode.APPLY
    details: dict = field(default_factory=dict)


@dataclass
class IndexOpsConfig:
    """Configuration for an ``IndexOps`` instance.

    Attributes:
        workdir: Root working directory.  Created automatically if absent.
        index_data_folder: Directory that holds the raw index data files.
        registry_dir: Path to the kmindex registry used to track sub-indexes.
        minimizer_length: K-mer minimizer size passed to the builder.
            Defaults to ``10``.
        sample_rootpath: Optional prefix prepended to every sample file path
            in an index definition.  Useful when paths are stored relative to
            a root that differs from the current working directory.
        kmindex_threads: Number of threads passed to kmindex build commands.
            Defaults to ``1``.
        kmindex_skip_compression: When ``True``, intermediate files are not
            compressed during the build.  Defaults to ``False``.
        kmindex_build_from: Override the parent index for all build operations,
            replacing the value declared in each index definition.
        filter_spans: If set, only process index definitions whose span value is
            in this list.
        filter_names: If set, only process index definitions whose name is in
            this list.
        on_existing: Behaviour when a sub-index folder already exists on disk but is not registered.
            Passed directly to the builder (e.g. ``"fail"``, ``"register"``).
            Defaults to ``"fail"``.
        fail_on_error: Abort the entire apply operation on the first build or
            merge error instead of continuing and returning ``PARTIAL``.
            Defaults to ``False``.
    """

    workdir: str
    index_data_folder: str
    registry_dir: str
    minimizer_length: int = 10
    sample_rootpath: Optional[str] = None
    kmindex_threads: int = 1
    kmindex_skip_compression: bool = False
    kmindex_build_from: Optional[str] = None
    filter_spans: Optional[list[int]] = None
    filter_names: Optional[list[str]] = None
    on_existing: str = "fail"
    fail_on_error: bool = False
    partition_count: Optional[int] = None


class IndexOps:
    """Orchestrates k-mer index build and merge operations against a kmindex registry.

    This class drives the full lifecycle of index management: loading index
    definitions or span registries from YAML/JSON files, building sub-indexes
    via ``IndexBuilder``, merging partial indexes into a combined index, and
    cleaning up superseded segments.  It supports a plan/dry-run mode that
    logs commands without executing them and can emit a shell script of the
    equivalent commands for manual replay.

    Args:
        config: Runtime configuration governing paths, build parameters,
            filtering, and execution behaviour.  See ``IndexOpsConfig``.

    Attributes:
        config (IndexOpsConfig): The resolved configuration (paths are
            converted to absolute paths on construction).
        work_dir (str): Absolute path to the working directory.
        asset_dir (str): ``<work_dir>/assets`` — output location for generated
            shell scripts.
        log_dir (str): ``<work_dir>/logs`` — log file destination.
        kmindex_registry_dir (str): Path to the kmindex registry directory.
        kmindex_data_dir (str): Path to the folder that holds index data.
        timestamp (str): ``YYYYmmdd_HHMMSS`` string captured at construction,
            used to name generated artefacts.

    Note:
        When ``dry_run=True`` is set in the config, ``plan`` is also forced
        to ``True`` and ``show_progress`` is disabled.  Build commands are
        collected internally and can be written to a shell script via
        ``write_script()``.
    """

    # MAGIC METHODS
    def __init__(self, config: IndexOpsConfig) -> None:
        self._config = config
        self._config.workdir = os.path.realpath(self.config.workdir)
        self._config.index_data_folder = os.path.realpath(self.config.index_data_folder)
        self._config.registry_dir = os.path.realpath(self.config.registry_dir)
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        self._mode = ApplyMode.APPLY

        self._dbs = dict[str, list[IndexDB]]()
        self._building = set[str]()
        self._script_lines = [
            "#!/usr/bin/bash",
            f"WORKDIR='{self.work_dir}'",
            "cd ${WORKDIR}",
        ]
        logger.debug(f"Init {type(self).__name__}")
        logger.debug("workdir: " + self.work_dir)
        logger.debug("registry_dir: " + self.kmindex_registry_dir)
        logger.debug("asset_dir: " + self.asset_dir)
        logger.debug("data_dir: " + self.kmindex_data_dir)

        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.asset_dir, exist_ok=True)
        os.makedirs(self.kmindex_registry_dir, exist_ok=True)
        os.makedirs(self.kmindex_data_dir, exist_ok=True)

    # ---
    # PROPERTIES AND GETTERS

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

    def write_script(self):
        """Write the collected build/merge commands to a timestamped shell script.

        The script is placed under ``asset_dir`` and named
        ``kmhelpers_apply_<timestamp>.sh``.  It is only meaningful after
        ``apply()`` has been called in plan or dry-run mode, since that is when
        commands are accumulated into ``_script_lines``.
        """
        script_path = os.path.join(self.asset_dir, f"kmhelpers_apply.sh")
        if os.path.exists(script_path):
            backup_path = script_path + ".bak"
            os.replace(script_path, backup_path)
            logger.debug(f"Backed up existing script to {backup_path}")
        with open(script_path, "w") as f:
            f.write("\n".join(self._script_lines) + "\n")
        logger.info(f"Script written to {script_path}")

    def run(self, path: str, mode: ApplyMode) -> ApplyResult:
        """Apply an index definition or span registry file to the kmindex registry.

        Reads ``path``, detects whether it is an index definition or a span
        registry, then builds any missing sub-indexes and merges partial indexes
        as required.  Skips any sub-index already present in the registry.

        Args:
            path: Path to a YAML or JSON file containing either an
                ``IndexDefinition`` or a span registry.

        Returns:
            An ``ApplyResult`` with the overall status and a per-index details
            dict.  Status is ``SUCCESS`` when all operations complete without
            error, ``PARTIAL`` when at least one operation fails but others
            succeed (only when ``fail_on_error=False``), or ``FAILED`` when a
            fatal error occurs before any index is built.
        """

        path = os.path.realpath(path)

        # Load desired state
        self._mode = mode
        result = ApplyResult()
        idt = IndexDefinitionTools()

        self._init_result(path, mode, result)
        data = self._deserialize_data(path, result, idt)

        if data is None or result.input_type is ApplyInputType.UNKNOWN:
            logger.error(f"Could not retrieve data type.")
            result.status = ApplyStatus.FAILED
            return result

        dbs = list[IndexDB]()
        merges = dict[str, list[str]]()
        builder = IndexBuilder(
            workdir=self.work_dir,
            registry_name=self.kmindex_registry_dir,
            data_folder=self.kmindex_data_dir,
            log_folder=self.log_dir,
        )

        try:
            if result.input_type is ApplyInputType.INDEX_DEFINITION:
                dbs = self._get_dbs(path, idt)
            elif result.input_type is ApplyInputType.SPAN_REGISTRY:
                dbs, merges = self._load_span_registry(path, idt, data)
        except Exception as e:
            Log.handle_exception(logger, e, f"Failed to load definition file '{path}'")
            result.status = ApplyStatus.FAILED
            return result

        for db in dbs:
            for i in db.index_table.values():

                if self._is_filtered(result, i) or not i.name:
                    continue

                logger.info(f"► Processing index definition '{i.name}'...")

                if builder.index.has_index(i.name):
                    logger.info(f"  └── {i.name} found in registry: skip")
                    self._record_run_result(result, i.name, ApplyStatus.NONE)
                    continue

                try:
                    self._update_span_stats(result, i)
                    self._build(result, builder, i)

                except Exception as e:
                    if self._handle_error(
                        result, e, f"   Failed to build index '{i.name}'", key=i.name
                    ):
                        return result

        for to_index, parts in merges.items():
            try:
                self._merge(result, builder, to_index, parts)

            except Exception as e:
                if self._handle_error(result, e, f"Failed to merge index '{to_index}'"):
                    return result

        result.status = ApplyStatus.SUCCESS
        return result

    # ---
    # PRIVATE METHODS

    def _update_span_stats(self, result, i):
        index_size = i.get_stored_size()
        sample_count = i.sample_count

        span_data = result.details["span"].setdefault(
            i.span, {"sample_count": 0, "bytes": 0, "size_str": "0B"}
        )
        span_data["sample_count"] += sample_count
        span_data["bytes"] += index_size.byte_count
        span_data["size_str"] = str(ByteCounter.auto(span_data["bytes"]))

        logger.info(f"  └── Sample count: {sample_count}")
        logger.info(f"  └── Estimated build size: {index_size}")

    def _is_filtered(self, result, i):
        # if ApplyInputType.SPAN_REGISTRY, filter has been already applied by _load_span_registry
        return result.input_type is ApplyInputType.INDEX_DEFINITION and (
            (self.config.filter_names and i.name not in self.config.filter_names)
            or (self.config.filter_spans and i.span not in self.config.filter_spans)
        )

    def _deserialize_data(self, path, result, idt):
        data = None
        if os.path.isfile(path) and path.endswith((".yaml", ".yml", ".json")):
            try:
                data = dict(idt.deserialize(path))
            except Exception as e:
                Log.handle_exception(
                    logger=logger, msg=f"Could not parse schema from {path}", e=e
                )
                return None

            if data:
                try:
                    type_value = data.get("type")
                    if type_value == SerializedDataType.INDEX_DEFINITION.value:
                        result.input_type = ApplyInputType.INDEX_DEFINITION
                    elif type_value == SerializedDataType.SPAN_DEFINITION.value:
                        result.input_type = ApplyInputType.SPAN_REGISTRY
                    else:
                        result.input_type = ApplyInputType.UNKNOWN
                except (ValueError, KeyError):
                    logger.error(f"Invalid type value: {data.get('type')}")
                    return None
        return data

    def _init_result(self, path, mode, result):
        result.mode = mode
        result.status = ApplyStatus.NONE
        result.input_type = ApplyInputType.UNKNOWN
        result.details = dict()
        result.details["input_file"] = path
        result.details["kmindex"] = {}
        result.details["span"] = {}
        result.details["run"] = {}
        wrapper = KmindexWrapper(dry_run=False)
        result.details["kmindex"]["version"] = wrapper.kmindex_version()
        result.details["kmindex"]["path"] = wrapper.which

    def _append_script(self, cmd: str) -> None:
        self._script_lines.append(cmd.replace(self.config.workdir, "${WORKDIR}"))

    def _record_run_result(
        self,
        result: ApplyResult,
        name: str,
        status: ApplyStatus,
        extra: str | None = None,
    ) -> None:
        value = f"[{status.value}]"
        if extra:
            value += f" {extra}"
        result.details["run"][name] = value

    def _handle_error(
        self,
        result: ApplyResult,
        e: Exception,
        msg: str,
        key: str | None = None,
    ) -> bool:
        """Log an error and update result status. Returns True if the caller should abort."""
        Log.handle_exception(logger, e, msg)
        if key:
            self._record_run_result(
                result, key, ApplyStatus.FAILED, Log.format_exception(e)
            )
        result.status = ApplyStatus.PARTIAL
        if self.config.fail_on_error:
            result.status = ApplyStatus.FAILED
            return True
        return False

    def _indent_prefix(self):
        return "  └── " if logger.isEnabledFor(logging.INFO) else ""

    def _run_build(self, builder: IndexBuilder, i: IndexDefinition):
        """Build a single sub-index, showing a progress spinner or bar if configured.

        Resolves sample file paths, populates a ``FofManager``, and delegates
        the actual build to ``IndexBuilder.create_subindex``.  The generated
        command is appended to ``_script_lines`` for later script export.

        Args:
            builder: The ``IndexBuilder`` instance managing the target registry.
            i: The index definition describing the sub-index to build.

        Returns:
            The result dict returned by ``IndexBuilder.create_subindex``, or
            ``None`` if the index was already building or no samples were added.
        """
        assert i.name, "IndexDefinition is missing required 'name' field"

        if i.name in self._building or builder.has_subindex(i.name):
            return None

        assert (
            i.bf_size
        ), f"IndexDefinition {i.name} is missing required 'bf_size' field"

        # --- Build FofManager from samples
        fof = FofManager()

        for s in i.samples.values():
            self._add_sample_to_fof(i, fof, s)

        result = None
        self._building.add(i.name)
        if fof.get_sample_count() > 0:
            # --- Progress handlers setup
            stop_event = None
            wait_handler = None
            progress_handler = None

            if self._mode == ApplyMode.APPLY_SHOW_PROGRESS:
                start = datetime.now()
                stop_event = threading.Event()

                def _progress_worker():
                    sleep(2)
                    s = 0
                    wait_steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
                    while not stop_event.wait(timeout=0.5):
                        print(
                            f"\r\033[1;32m{wait_steps[s]} Building index '{i.name}'...\033[0m ",
                            end="",
                            flush=True,
                        )
                        s = (s + 1) % len(wait_steps)

                wait_handler = threading.Thread(target=_progress_worker, daemon=True)
                wait_handler.start()

                def _on_progress(value: float):
                    elapsed = (datetime.now() - start).total_seconds()
                    bar_len = 30
                    filled = int(round(bar_len * value))
                    bar = "■" * filled + " " * (bar_len - filled)
                    print(
                        f"\r[{bar}] {value * 100:.1f}%  elapsed: {int(elapsed // 60)}m{int(elapsed % 60):02d}s      ",
                        end="",
                        flush=True,
                    )
                    if stop_event:
                        stop_event.set()

                    if wait_handler:
                        wait_handler.join()

                progress_handler = IndexBuilder.Progress(_on_progress, delay=60)
            elif self._mode >= ApplyMode.APPLY:
                logger.info(f"  └── Building '{i.name}'...")

            # --- Call builder
            try:
                partition_count = (
                    self.config.partition_count
                    if self.config.partition_count
                    else i.partition_count
                )
                result = builder.create_subindex(
                    name=i.name,
                    samples=fof,
                    abundance_min=i.abundance_min,
                    bloom_size=i.bf_size,
                    n_partitions=partition_count,
                    n_threads=self.config.kmindex_threads,
                    auto_check=True,
                    compress_intermediate=not self.config.kmindex_skip_compression,
                    minim_size=self.config.minimizer_length,
                    dry_run=self._mode < ApplyMode.APPLY,
                    kmer_size=i.kmer_size,
                    on_existing=self.config.on_existing,
                    progress=progress_handler,
                )
                if result and "command" in result:
                    self._append_script(result["command"])
            finally:
                if stop_event:
                    stop_event.set()
                if wait_handler:
                    wait_handler.join()

            # --- Post-build verification
            if self._mode >= ApplyMode.APPLY:
                builder.index.load_json()
                assert builder.has_subindex(i.name), f"Could not find index '{i.name}'"
        else:
            logger.warning(
                f"{self._indent_prefix()}Skipping index '{i.name}' as no sample was added to it"
            )

        return result

    def _add_sample_to_fof(self, i: IndexDefinition, fof: FofManager, s: Sample):
        try:
            if not s.name:
                raise ValueError("Empty name")
            if not s.files:
                raise ValueError("Empty file list")
            if s.name != "_":
                sample_files = (
                    [os.path.join(self.config.sample_rootpath, f) for f in s.files]
                    if self.config.sample_rootpath
                    else s.files
                )
                if self._mode > ApplyMode.DRY_RUN:
                    for f in sample_files:
                        assert os.path.isfile(f), f"Sample file not found: {f}"
                fof.add_sample(sample_files, s.name)
        except Exception as e:
            logger.warning(
                f"{self._indent_prefix()}Error adding sample '{s.name or "UNNAMED"}' to '{i.name}' | {e}"
            )

    def _get_dbs(self, path, idt):
        """Load and cache ``IndexDB`` objects from a definition file.

        Args:
            path: Absolute path to the definition file.
            idt: ``IndexDefinitionTools`` instance used for deserialization.

        Returns:
            A list of ``IndexDB`` objects loaded from ``path``.  Subsequent
            calls with the same path return the cached result without re-reading
            the file.
        """
        if path in self._dbs:
            dbs = self._dbs[path]
        else:
            dbs = idt.load_db(path)
            self._dbs[path] = dbs
        return dbs

    def _load_span_registry(self, path, idt, data) -> tuple[list, dict]:
        """Parse a span registry and return ``(dbs, merges)``.

        Iterates over each span in the registry, optionally filtering by
        ``config.filter_spans`` and ``config.filter_names``.  For each index
        that passes the filter, the merge target and its constituent sub-index
        names are recorded in ``merges``, and the corresponding definition files
        are loaded into ``dbs``.

        Args:
            path: Absolute path to the span registry file (used to resolve
                sibling definition files).
            idt: ``IndexDefinitionTools`` instance for loading definition files.
            data: Deserialized registry dict (``{"data": {span_id: {...}}}``)

        Returns:
            A ``(dbs, merges)`` tuple where ``dbs`` is a list of ``IndexDB``
            objects and ``merges`` maps each merge target to its sub-index names.

        Raises:
            AssertionError: If a span entry is missing the ``"indices"`` field
                or a required definition file does not exist on disk.
        """
        dbs = list[IndexDB]()
        merges = dict[str, list[str]]()
        spans = dict[int, dict](data["data"])
        for to_index, parts in spans.items():
            if self.config.filter_spans and to_index not in self.config.filter_spans:
                continue
            parts = parts.get("indices")
            assert parts, f"Span registry is missing field 'indices'"
            indices = dict[str, list[str]](parts)
            for name, subindices in indices.items():
                if not self.config.filter_names or name in self.config.filter_names:
                    merges[name] = subindices

                for subindex in subindices:
                    if name in merges or (
                        self.config.filter_names
                        and subindex in self.config.filter_names
                    ):
                        db_path = os.path.join(
                            os.path.dirname(path),
                            subindex + os.path.splitext(path)[1],
                        )
                        assert os.path.isfile(
                            db_path
                        ), f"Could not find required data file at {db_path}"
                        dbs.extend(self._get_dbs(db_path, idt))
        return dbs, merges

    def _build(self, result, builder, i):
        """Build a sub-index and record the outcome in ``result``.

        Args:
            result: The ``ApplyResult`` being accumulated; ``details`` is
                updated in place.
            builder: The ``IndexBuilder`` managing the target registry.
            i: The ``IndexDefinition`` of the index to build.

        Raises:
            AssertionError: If ``bf_size`` is not set on the definition.
        """
        assert (
            i.bf_size > 0
        ), f"IndexDefinition {i.name} is missing required 'bf_size' field"

        builder.index.load_json()
        build_result = self._run_build(builder, i)
        if build_result:
            if self._mode < ApplyMode.APPLY or build_result.get("return_code", -1) == 0:
                self._record_run_result(result, i.name, ApplyStatus.SUCCESS)
            else:
                self._record_run_result(
                    result,
                    i.name,
                    ApplyStatus.FAILED,
                    f"error_code={build_result['return_code']}",
                )
        else:
            self._record_run_result(result, i.name, ApplyStatus.NONE)

    def _merge(self, result, builder, to_index, parts):
        """Merge a list of sub-indexes into a combined index and clean up the parts.

        Verifies that all constituent sub-indexes are present in the registry
        (skipped in plan mode), calls ``IndexBuilder.merge``, and if the
        resulting index passes a structure check, removes each constituent
        segment via ``_delete_segment``.

        Args:
            result: The ``ApplyResult`` being accumulated; ``details`` is
                updated in place.
            builder: The ``IndexBuilder`` managing the target registry.
            to_index: Name of the target merged index.
            parts: List of sub-index names to merge into ``to_index``.

        Raises:
            Exception: If the builder returns a malformed result dict.
            AssertionError: If the merged sub-index is not found in the registry
                after the merge.
        """
        builder.index.load_json()
        missing = None

        if self._mode >= ApplyMode.APPLY:
            missing = [name for name in parts if not builder.index.has_index(name)]

        if missing:
            logger.warning(
                f"Cannot merge '{to_index}' due to some sub-indexes missing: {missing}"
            )
            result.details[to_index] = (
                f"[{ApplyStatus.FAILED.value}] Missing sub-indexes: {missing}"
            )
        else:
            merge_result = builder.merge(
                to_index,
                parts,
                delete_old=False,
                dry_run=self._mode < ApplyMode.APPLY,
                threads=self._config.kmindex_threads,
            )

            if merge_result and "command" in merge_result:
                self._append_script(merge_result["command"])
                result.details[to_index] = f"[{ApplyStatus.SUCCESS.value}]"
            else:
                raise Exception("Malformed result")

            if self._mode >= ApplyMode.APPLY:
                builder.index.load_json()
                assert builder.has_subindex(to_index), f"Sub-index {to_index} not found"
                if builder.index.get_index(to_index).check_structure():
                    for segment in parts:
                        self._delete_segment(builder, segment)

    def _delete_segment(self, builder, segment):
        """Remove a segment sub-index from the registry and delete its files.

        Unregisters ``segment`` from the kmindex registry (ignoring it if
        already unregistered), then removes the corresponding directory under
        ``index_data_folder`` and any dangling symlink at that path.  Failures
        during file deletion are logged as warnings rather than raised.

        Args:
            builder: The ``IndexBuilder`` whose registry entry should be removed.
            segment: Name of the sub-index segment to delete.
        """
        logger.info(f"Delete {segment}...")

        # --- Unregister from registry
        try:
            builder.index.remove_index(
                segment, delete_files=False, skip_unregistered=True
            )
        except Exception as e:
            logger.warning(f"Failed to remove {segment} from registry: {e}")

        index_path = os.path.join(self.config.index_data_folder, segment)

        # --- Delete files from disk
        if self._mode >= ApplyMode.APPLY:
            try:
                # Get index before removal (needed to delete files)
                shutil.rmtree(
                    os.path.realpath(index_path),
                    ignore_errors=True,
                )
            except Exception as e:
                Log.handle_exception(
                    logger,
                    e,
                    f"Failed to delete some files",
                    logging.WARNING,
                )

            try:
                if os.path.islink(index_path):
                    os.unlink(index_path)
            except Exception as e:
                Log.handle_exception(
                    logger,
                    e,
                    f"Error deleting link {index_path}",
                    logging.WARNING,
                )

            if os.path.exists(index_path):
                logging.warning(
                    f"Could not remove dir {index_path}, please remove it manually."
                )
        else:
            self._append_script(f"rm -rf $(realpath {index_path})")
            self._append_script(f"[ -L {index_path} ] && unlink {index_path}")

    # ---
