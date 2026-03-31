import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import sleep
from typing import Optional

from pykmhelpers.core.log import Log
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import (
    IndexDB,
    IndexDefinition,
    IndexDefinitionTools,
    SerializedDataType,
)

logger = logging.getLogger(__name__)


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
        plan: When ``True``, commands are logged and collected for script
            output but not executed.  Defaults to ``False``.
        dry_run: Implies ``plan=True``.  Skips file existence checks in
            addition to not executing commands.  Defaults to ``False``.
        on_existing: Behaviour when a sub-index folder already exists on disk but is not registered.
            Passed directly to the builder (e.g. ``"fail"``, ``"register"``).
            Defaults to ``"fail"``.
        show_progress: Display a progress bar with ETA during builds.
            Disabled automatically in plan/dry-run mode.  Defaults to ``False``.
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
    plan: bool = False
    dry_run: bool = False
    on_existing: str = "fail"
    show_progress: bool = False
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

    # PRIVATE METHODS
    def __init__(self, config: IndexOpsConfig) -> None:
        self._config = config
        self._config.workdir = os.path.realpath(self.config.workdir)
        self._config.index_data_folder = os.path.realpath(self.config.index_data_folder)
        self._config.registry_dir = os.path.realpath(self.config.registry_dir)
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.config
        if self._config.dry_run:
            self._config.plan = True
        if self._config.dry_run or self._config.plan:
            self._config.show_progress = False
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
        script_path = os.path.join(
            self.asset_dir, f"kmhelpers_apply_{self.timestamp}.sh"
        )
        with open(script_path, "w") as f:
            f.write("\n".join(self._script_lines) + "\n")
        logger.info(f"Script written to {script_path}")

    def compose(self):
        """Compose an index definition from the current configuration. (Not yet implemented.)"""
        pass

    def plan(self, def_file: str):
        """Preview the operations that would be performed for a definition file. (Not yet implemented.)

        Args:
            def_file: Path to the index definition or span registry file to
                inspect.
        """
        pass

    def apply(self, path: str) -> ApplyResult:
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
        result = ApplyResult()
        idt = IndexDefinitionTools()

        result.status = ApplyStatus.NONE
        result.input_type = ApplyInputType.UNKNOWN
        result.details = dict()
        result.details["input_file"] = path
        idt = IndexDefinitionTools()
        data = None

        if os.path.isfile(path) and path.endswith((".yaml", ".yml", ".json")):
            try:
                data = dict(idt.deserialize(path))
            except Exception as e:
                Log.handle_exception(
                    logger=logger, msg=f"Could not parse schema from {path}", e=e
                )

            if data:
                try:
                    result.input_type = (
                        ApplyInputType.INDEX_DEFINITION
                        if data.get("type") == SerializedDataType.INDEX_DEFINITION.value
                        else (
                            ApplyInputType.SPAN_REGISTRY
                            if data.get("type")
                            == SerializedDataType.SPAN_DEFINITION.value
                            else ApplyInputType.UNKNOWN
                        )
                    )
                except (ValueError, KeyError):
                    logger.error(f"Invalid type value: {data.get('type')}")

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

        if result.input_type is ApplyInputType.INDEX_DEFINITION:
            try:
                dbs = self._get_dbs(path, idt)
            except Exception as e:
                Log.handle_exception(
                    logger, e, f"Failed to load definition file '{path}'"
                )
                result.status = ApplyStatus.FAILED
                return result
        elif result.input_type is ApplyInputType.SPAN_REGISTRY:
            try:
                self._load_span_registry(path, idt, data, dbs, merges)

            except Exception as e:
                Log.handle_exception(
                    logger, e, f"Failed to load definition file '{path}'"
                )
                result.status = ApplyStatus.FAILED
                return result
            pass

        for db in dbs:
            for i in db.index_table.values():

                if result.input_type is ApplyInputType.INDEX_DEFINITION and (
                    (
                        self.config.filter_names
                        and i.name not in self.config.filter_names
                    )
                    or (
                        self.config.filter_spans
                        and i.span not in self.config.filter_spans
                    )
                ):
                    continue

                logger.info(f"Processing index definition '{i.name}'...")

                assert i.name, "IndexDefinition is missing required 'name' field"
                if builder.index.has_index(i.name):
                    logger.info(f"{i.name} found in registry: skip")
                    result.details[i.name] = f"[{ApplyStatus.NONE.value}]"
                    continue

                parent_index = i.get_parent()

                if self.config.kmindex_build_from:
                    parent_index = self.config.kmindex_build_from

                try:
                    self._build(path, result, idt, builder, i, parent_index)

                except Exception as e:
                    Log.handle_exception(logger, e, f"Failed to build index '{i.name}'")
                    result.details[i.name] = (
                        f"[{ApplyStatus.FAILED.value}] {Log.format_exception(e)}"
                    )
                    result.status = ApplyStatus.PARTIAL
                    if self.config.fail_on_error:
                        result.status = ApplyStatus.FAILED
                        return result

        for to_index, parts in merges.items():
            try:
                self._merge(result, builder, to_index, parts)

            except Exception as e:
                Log.handle_exception(logger, e, f"Failed to merge index '{to_index}'")
                result.details[to_index] = (
                    f"[{ApplyStatus.FAILED.value}] {Log.format_exception(e)}"
                )
                result.status = ApplyStatus.PARTIAL
                if self.config.fail_on_error:
                    result.status = ApplyStatus.FAILED
                    return result

        result.status = ApplyStatus.SUCCESS
        return result

    def _build_single(self, builder: IndexBuilder, i: IndexDefinition):
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

        parent_index = i.get_parent()

        if self.config.kmindex_build_from:
            parent_index = self.config.kmindex_build_from

        if parent_index and not self.config.plan:
            assert builder.has_subindex(
                parent_index
            ), f"Could not find index '{parent_index}' required to build index '{i.name}'"

        fof = FofManager()

        for s in i.samples.values():
            if s.name and s.name != "_":
                try:
                    sample_files = (
                        [os.path.join(self.config.sample_rootpath, f) for f in s.files]
                        if self.config.sample_rootpath
                        else s.files
                    )
                    if not self.config.dry_run:
                        for f in sample_files:
                            assert os.path.isfile(f), f"Sample file not found: {f}"
                    fof.add_sample(sample_files, s.name)
                except Exception as e:
                    logger.warning(f"Error adding sample '{s.name}' to index | {e}")

        result = None
        self._building.add(i.name)
        if fof.get_sample_count() > 0:
            stop_event = None
            wait_handler = None
            progress_handler = None
            if self.config.show_progress:

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
            else:
                logger.info(f"Building index '{i.name}'...")

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
                    build_from=parent_index,
                    compress_intermediate=not self.config.kmindex_skip_compression,
                    minim_size=self.config.minimizer_length,
                    dry_run=self.config.plan,
                    kmer_size=i.kmer_size,
                    on_existing=self.config.on_existing,
                    progress=progress_handler,
                )
                if result and "command" in result:
                    self._script_lines.append(
                        result["command"].replace(self.config.workdir, "${WORKDIR}")
                    )
            except:
                raise
            finally:
                if stop_event:
                    stop_event.set()
                if wait_handler:
                    wait_handler.join()
        else:
            logger.warning(f"Skipping index '{i.name}' as no sample was added to it")

        if not self.config.plan:
            builder.index.load_json()
            assert builder.has_subindex(i.name), f"Could not find index '{i.name}'"

        return result

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

    def _find_definition(
        self, name: str, source_file: str, idt: IndexDefinitionTools
    ) -> IndexDefinition:
        """Look up an ``IndexDefinition`` by name across all loaded databases.

        Searches already-cached databases first.  If not found, constructs a
        sibling file path (same directory and extension as ``source_file``,
        named ``<name>.<ext>``) and attempts to load it.

        Args:
            name: Name of the index definition to find.
            source_file: Path of the file that referenced this index, used to
                resolve sibling definition files.
            idt: ``IndexDefinitionTools`` instance used to load sibling files.

        Returns:
            The matching ``IndexDefinition``.

        Raises:
            FileNotFoundError: If the sibling file does not exist.
            AssertionError: If the definition is still not found after loading
                the sibling file.
        """
        res = None

        for l in self._dbs.values():
            for db in l:
                print(db.index_table.keys())
                if name in db.index_table:
                    return db.index_table[name]

        if not res:
            db_path = os.path.join(
                os.path.dirname(source_file),
                name + os.path.splitext(source_file)[1],
            )
            if os.path.isfile(db_path):
                db = self._get_dbs(db_path, idt)
                for d in db:
                    if name in d.index_table:
                        res = d.index_table[name]
            else:
                raise FileNotFoundError(db_path)
        assert res, f"Could not find definition for required index {name}"
        return res

    # def _assert_field(self, field):
    #     assert self.has_field_in_config(field), f"Field '{field}' not found in config"

    # def _check_config(self):
    #     self._assert_field("workdir")
    #     self._assert_field("")

    # def has_field_in_config(self, field_name: str) -> bool:
    #     return field_name in self._config

    def _load_span_registry(self, path, idt, data, dbs, merges):
        """Parse a span registry and populate the ``dbs`` and ``merges`` structures.

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
            dbs: List to extend with loaded ``IndexDB`` objects.
            merges: Dict to populate with ``{merge_target: [sub_index_names]}``.

        Raises:
            AssertionError: If a span entry is missing the ``"indices"`` field
                or a required definition file does not exist on disk.
        """
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

    def _build(self, path, result, idt, builder, i, parent_index):
        """Build a sub-index, first building its parent if necessary.

        If ``parent_index`` is specified and not yet present in the registry,
        the parent's definition is resolved via ``_find_definition`` and built
        first.  The target index ``i`` is then built via ``_build_single``.
        Build outcomes are written into ``result.details``.

        Args:
            path: Source definition file path, forwarded to ``_find_definition``
                for sibling lookups.
            result: The ``ApplyResult`` being accumulated; ``details`` is
                updated in place.
            idt: ``IndexDefinitionTools`` for loading sibling definition files.
            builder: The ``IndexBuilder`` managing the target registry.
            i: The ``IndexDefinition`` of the index to build.
            parent_index: Name of the required parent index, or ``None``.

        Raises:
            AssertionError: If ``bf_size`` is not set on the definition.
        """
        assert (
            i.bf_size > 0
        ), f"IndexDefinition {i.name} is missing required 'bf_size' field"

        if (
            parent_index
            and parent_index not in self._building
            and not builder.has_subindex(parent_index)
        ):
            parent_def = self._find_definition(parent_index, path, idt)
            builder.index.load_json()
            logger.debug(f"Building required parent index '{parent_index}'")
            build_result = self._build_single(builder, parent_def)
            if build_result:
                if build_result["return_code"] == 0:
                    result.details[i.name] = f"[{ApplyStatus.SUCCESS.value}]"
                else:
                    result.details[i.name] = (
                        f"[{ApplyStatus.FAILED.value}] error_code={build_result["return_code"]}"
                    )
        else:
            result.details[i.name] = f"[{ApplyStatus.NONE.value}]"

        builder.index.load_json()
        build_result = self._build_single(builder, i)
        if build_result:
            if build_result["return_code"] == 0:
                result.details[i.name] = f"[{ApplyStatus.SUCCESS.value}]"
            else:
                result.details[i.name] = (
                    f"[{ApplyStatus.FAILED.value}] error_code={build_result["return_code"]}"
                )
        else:
            result.details[i.name] = f"[{ApplyStatus.NONE.value}]"

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
        if not self.config.plan:
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
                dry_run=self.config.plan,
            )

            if result and "command" in merge_result:
                self._script_lines.append(
                    merge_result["command"].replace(self.config.workdir, "${WORKDIR}")
                )
                result.details[to_index] = f"[{ApplyStatus.SUCCESS.value}]"
            else:
                raise Exception("Malformed result")

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
        logging.info(f"Delete {segment}...")
        try:
            builder.index.remove_index(
                segment, delete_files=False, skip_unregistered=True
            )

        except Exception as e:
            logger.warning(f"Failed to remove {segment} from registry: {e}")

        index_path = os.path.join(self.config.index_data_folder, segment)

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

    # ---
