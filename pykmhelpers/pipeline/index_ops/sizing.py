import logging
from dataclasses import dataclass
from typing import Optional

from pykmhelpers.core.bloom_filter import bf_max_kmers
from pykmhelpers.core.build_params import auto_params
from pykmhelpers.pipeline.index_db import IndexDefinition
from pykmhelpers.pipeline.index_ops.types import IndexOpsConfig

logger = logging.getLogger(__name__)

# kmtricks silently raises any lower --nb-partitions value to this floor
KMTRICKS_MIN_PARTITIONS = 4


def clamp_partitions(count: int) -> int:
    """Apply the kmtricks partition floor; 0 (auto) is left untouched."""
    return max(count, KMTRICKS_MIN_PARTITIONS) if count > 0 else count


@dataclass(frozen=True)
class BuildParams:
    """Resolved kmindex build parameters for one index.

    ``chunk_size`` is set when the open-files ceiling can't fit every sample
    in one kmtricks build: the build must then be split into chunks of at
    most ``chunk_size`` samples and merged.
    """

    threads: int
    partitions: int
    chunk_size: Optional[int] = None


def resolve_build_params(
    i: IndexDefinition, sample_count: int, config: IndexOpsConfig
) -> BuildParams:
    """Resolve the build parameters of index ``i`` holding ``sample_count`` samples.

    If ``config.kmindex_threads`` is set, it is used as-is together with the
    storage-driven partition count computed by ``IndexComposer``
    (``i.partition_count``), and no chunking is applied.

    Otherwise threads and a RAM-driven partition floor come from
    ``auto_params``. The partition count is never lower than the
    storage-driven value, since both constrain the same ``--nb-partitions``
    flag.

    ``i`` is not modified; callers update ``i.partition_count`` so size
    estimates match what will be built.
    """
    partitions = clamp_partitions(config.partition_count or i.partition_count)

    if config.kmindex_threads:
        return BuildParams(config.kmindex_threads, partitions)

    params = auto_params(
        kmers=bf_max_kmers(i.bf_size, i.fp_rate),
        samples=sample_count,
        limits=config.limits or "{}",
        safety_margin=config.safety_margin,
    )
    if params.threads is None or params.samples is None or params.partitions is None:
        raise TypeError(
            f"expected auto_params() to set threads/samples/partitions, got "
            f"threads={params.threads!r}, samples={params.samples!r}, "
            f"partitions={params.partitions!r}"
        )

    chunk_size = params.samples if params.samples < sample_count else None
    if chunk_size is not None:
        logger.info(
            f"  └── '{i.name}' has {sample_count} samples, exceeding the "
            f"{chunk_size} a single kmtricks build can fit under the "
            f"current open-files limit; splitting into chunks"
        )

    partitions = clamp_partitions(max(partitions, params.partitions))
    logger.info(f"  └── Auto-sized: threads={params.threads}, partitions={partitions}")
    return BuildParams(params.threads, partitions, chunk_size)
