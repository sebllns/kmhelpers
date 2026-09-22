from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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
            ``None`` (or ``0``) auto-sizes threads per index from ``limits``
            (system RAM/ulimit by default, scaled by ``safety_margin``) via
            ``auto_params``. Defaults to ``None``.
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
        limits: JSON line of resource limits (``ram``, ``files``, ``threads``,
            ``focus``) forwarded to ``auto_params`` when
            ``kmindex_threads`` is unset. Any key omitted is auto-detected
            from the system. Defaults to ``None`` (all keys auto-detected).
        safety_margin: Fraction of a detected system limit to use for any
            key missing from ``limits``. Defaults to ``0.9``.
        session_assets: When ``True``, generated assets and scripts go to
            ``assets/<session>/``, where the session is the folder name of the
            input file, and ``assets/kmhelpers_apply.sh`` runs the last
            session. Defaults to ``False`` (flat ``assets/``).
    """

    workdir: str
    index_data_folder: str
    registry_dir: str
    minimizer_length: int = 10
    sample_rootpath: Optional[str] = None
    kmindex_threads: Optional[int] = None
    kmindex_skip_compression: bool = False
    kmindex_build_from: Optional[str] = None
    filter_spans: Optional[list[int]] = None
    filter_names: Optional[list[str]] = None
    on_existing: str = "fail"
    partition_count: Optional[int] = None
    limits: Optional[str] = None
    safety_margin: float = 0.9
    session_assets: bool = False
