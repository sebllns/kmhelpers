import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from time import sleep
from typing import Optional

from ..core.log import Log
from ..operations.builder import IndexBuilder
from ..pipeline.fof import FofManager
from .index_db import IndexDB, IndexDefinition, IndexDefinitionTools, SerializedDataType

logger = logging.getLogger(__name__)


class ApplyStatus(str, Enum):
    """Status of an apply operation."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NONE = "NONE"


class ApplyInputType(str, Enum):
    UNKNOWN = "unknown"
    SPAN_REGISTRY = "span registry"
    INDEX_DEFINITION = "index definition"
    NONE = "none"


@dataclass
class ApplyResult:
    status: ApplyStatus = ApplyStatus.NONE
    input_type: ApplyInputType = ApplyInputType.NONE
    details: dict = field(default_factory=dict)


@dataclass
class IndexOpsConfig:
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


class IndexOps:
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
            f"WORKDIR='{self.config.workdir}'",
            "cd ${WORKDIR}",
        ]
        logger.debug(f"Init {type(self).__name__}")
        logger.debug("workdir: " + config.workdir)
        if not os.path.exists(config.workdir):
            logger.info(f"Creating 'workdir' at {config.workdir}")
            os.makedirs(config.workdir, exist_ok=True)

    def _build_single(self, builder: IndexBuilder, i: IndexDefinition):

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
                        [self.config.sample_rootpath + f for f in s.files]
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
            if not self.config.dry_run and not self.config.plan:
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

            else:
                logger.info(f"Building index '{i.name}'...")

            progress_handler = None
            if self.config.show_progress:

                start = datetime.now()

                def _on_progress(value: float):
                    elapsed = (datetime.now() - start).total_seconds()
                    if value > 0:
                        estimated_total = elapsed / value
                        remaining = estimated_total - elapsed
                        mins, secs = divmod(int(remaining), 60)
                        eta = f"~{mins}m{secs:02d}s remaining"
                    else:
                        eta = "estimating..."
                    bar_len = 30
                    filled = int(round(bar_len * value))
                    bar = "■" * filled + " " * (bar_len - filled)
                    print(
                        f"\r[{bar}] {value * 100:.1f}%  elapsed: {int(elapsed // 60)}m{int(elapsed % 60):02d}s  {eta}",
                        end="",
                        flush=True,
                    )
                    if stop_event:
                        stop_event.set()

                    if wait_handler:
                        wait_handler.join()

                progress_handler = IndexBuilder.Progress(_on_progress, delay=60)

            try:
                result = builder.create_subindex(
                    name=i.name,
                    samples=fof,
                    abundance_min=i.abundance_min,
                    bloom_size=i.bf_size,
                    n_partitions=i.partition_count,
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
        if path in self._dbs:
            dbs = self._dbs[path]
        else:
            dbs = idt.load_db(path)
            self._dbs[path] = dbs
        return dbs

    def _find_definition(
        self, name: str, source_file: str, idt: IndexDefinitionTools
    ) -> IndexDefinition:
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
    def compose(self):
        pass

    def plan(self, def_file: str):
        pass

    def apply(self, path: str) -> ApplyResult:
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
                spans = dict[int, dict](data["data"])
                for k, v in spans.items():
                    if self.config.filter_spans and k not in self.config.filter_spans:
                        continue
                    v = v.get("indices")
                    assert v, f"Span registry is missing field 'indices'"
                    indices = dict[str, list[str]](v)
                    for name, subindices in indices.items():
                        if (
                            not self.config.filter_names
                            or name in self.config.filter_names
                        ):
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
                parent_index = i.get_parent()

                if self.config.kmindex_build_from:
                    parent_index = self.config.kmindex_build_from

                try:
                    assert i.name, "IndexDefinition is missing required 'name' field"
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
                                result.details[i.name] = (
                                    f"[{ApplyStatus.SUCCESS.value}]"
                                )
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

                except Exception as e:
                    Log.handle_exception(logger, e, f"Failed to build index '{i.name}'")
                    result.details[i.name] = (
                        f"[{ApplyStatus.FAILED.value}] {Log.format_exception(e)}"
                    )
                    result.status = ApplyStatus.PARTIAL
                    if self.config.fail_on_error:
                        result.status = ApplyStatus.FAILED
                        return result

        for k, v in merges.items():
            try:
                # if len(v) > 0:
                builder.index.load_json()
                missing = None
                if not self.config.plan:
                    missing = [name for name in v if not builder.index.has_index(name)]
                if missing:
                    logger.warning(
                        f"Sub-indexes to merge not found in registry: {missing}"
                    )
                    logger.warning(
                        f"Cannot merge '{k}' due to some sub-indexes missing"
                    )
                    result.details[k] = (
                        f"[{ApplyStatus.FAILED.value}] Missing sub-indexes: {missing}"
                    )
                else:
                    merge_result = builder.merge(
                        k, v, delete_old=False, dry_run=self.config.plan
                    )
                    builder.index.load_json()
                    assert builder.has_subindex(k), f"Sub-index {k} not found"
                    for vv in v:
                        try:
                            builder.index.remove_index(vv, delete_files=True)
                        except:
                            logger.warning(f"Failed to remove {vv} from registry.")
                    if result and "command" in merge_result:
                        self._script_lines.append(
                            merge_result["command"].replace(
                                self.config.workdir, "${WORKDIR}"
                            )
                        )
                        result.details[k] = f"[{ApplyStatus.SUCCESS.value}]"
                    else:
                        raise Exception("Malformed result")
            # elif self.config.plan:
            #     self._script_lines.append(f"mv {v[0]} {k}")
            # else:
            #     builder.index.load_json()
            #     builder.index.rename_index(v[0], k)
            except Exception as e:
                Log.handle_exception(logger, e, f"Failed to merge index '{k}'")
                result.details[k] = (
                    f"[{ApplyStatus.FAILED.value}] {Log.format_exception(e)}"
                )
                result.status = ApplyStatus.PARTIAL
                if self.config.fail_on_error:
                    result.status = ApplyStatus.FAILED
                    return result

        result.status = ApplyStatus.SUCCESS
        return result

    def write_script(self):
        script_path = os.path.join(
            self.asset_dir, f"kmhelpers_apply_{self.timestamp}.sh"
        )
        with open(script_path, "w") as f:
            f.write("\n".join(self._script_lines) + "\n")
        logger.info(f"Script written to {script_path}")

    # ---
