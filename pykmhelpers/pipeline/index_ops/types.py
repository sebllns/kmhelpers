from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pykmhelpers.core.constants import CHUNK_BUDGET, MAX_CHUNKS


class ApplyMode(int, Enum):
    DRY_RUN = 0
    PLAN = 1
    APPLY = 2
    APPLY_SHOW_PROGRESS = 3

    @property
    def executes(self) -> bool:
        """True when commands are actually run (not just planned)."""
        return self >= ApplyMode.APPLY

    @property
    def checks_files(self) -> bool:
        """True when sample files must exist on this machine."""
        return self > ApplyMode.DRY_RUN


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
        INDEX_SESSION: Input is the session file (``SESSION/index.yaml``) of
            an index, listing the shards its parts are merged into.
        INDEX_DEFINITION: Input is an index definition file describing one or
            more sub-indexes to build.
        NONE: No input file has been inspected yet.
    """

    UNKNOWN = "unknown"
    INDEX_SESSION = "index session"
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
        workdir: ``BUILD_DIR``, the kmindex registry: published indexes are
            its subdirectories (see ``BuildPaths``). Created if absent.
        sample_rootpath: Optional prefix prepended to every sample file path
            in an index definition.  Useful when paths are stored relative to
            a root that differs from the current working directory.
        kmindex_threads: Number of threads passed to kmindex build commands.
            ``None`` (or ``0``) auto-sizes threads per index from ``limits``
            (system RAM/ulimit by default, scaled by ``safety_margin``) via
            ``auto_params``. Defaults to ``None``.
        kmindex_skip_compression: When ``True``, intermediate files are not
            compressed during the build.  Defaults to ``False``.
        kmindex_build_from: Override the parent index for all build operations,
            replacing the value declared in each index definition.
        filter_names: If set, only process the shards (or parts) whose name
            matches one of these glob patterns.
        filter_runs: If set, only build the kmtricks runs (``<part>`` or
            ``<part>_chunk<N>``) matching one of these glob patterns, and
            publish nothing.
        limits: JSON line of resource limits (``ram``, ``files``, ``threads``,
            ``focus``) forwarded to ``auto_params`` when
            ``kmindex_threads`` is unset. Any key omitted is auto-detected
            from the system. Defaults to ``None`` (all keys auto-detected).
        safety_margin: Fraction of a detected system limit to use for any
            key missing from ``limits``. Defaults to ``0.9``.
        max_chunks: Cap on the number of chunks a shard is built in. A
            bigger chunk needs more open files in the merge stage, so the cap
            is paid for with threads. ``0`` disables it, leaving the chunk
            size to the open-files limit alone. Defaults to ``MAX_CHUNKS``.
        chunk_budget: K-mer budget of one kmtricks chunk: a chunk of span s
            holds at most ``ceil8(chunk_budget / base**s)`` samples. ``0``
            for no limit. Defaults to ``CHUNK_BUDGET``.
        keep_previous: Keep the replaced version of an updated index in
            ``work/<session>/previous/`` instead of deleting it. Defaults to
            ``False``.
    """

    workdir: str
    sample_rootpath: Optional[str] = None
    kmindex_threads: Optional[int] = None
    kmindex_skip_compression: bool = False
    kmindex_build_from: Optional[str] = None
    filter_names: Optional[list[str]] = None
    filter_runs: Optional[list[str]] = None
    limits: Optional[str] = None
    safety_margin: float = 0.9
    max_chunks: int = MAX_CHUNKS
    chunk_budget: int = CHUNK_BUDGET
    keep_previous: bool = False
