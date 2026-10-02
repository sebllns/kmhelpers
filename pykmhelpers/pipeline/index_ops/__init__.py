"""Build and merge k-mer indexes from index definitions or span registries.

``IndexOps`` is the entry point; the other modules are its components.
"""

from pykmhelpers.pipeline.index_ops.ops import IndexOps
from pykmhelpers.pipeline.index_ops.sizing import (
    KMTRICKS_MIN_PARTITIONS,
    BuildParams,
    clamp_partitions,
)
from pykmhelpers.pipeline.index_ops.types import (
    ApplyInputType,
    ApplyMode,
    ApplyResult,
    ApplyStatus,
    IndexOpsConfig,
)

__all__ = [
    "IndexOps",
    "IndexOpsConfig",
    "ApplyMode",
    "ApplyStatus",
    "ApplyInputType",
    "ApplyResult",
    "BuildParams",
    "clamp_partitions",
    "KMTRICKS_MIN_PARTITIONS",
]
