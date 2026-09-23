import logging
from dataclasses import dataclass
from typing import Optional

from pykmhelpers.core.bloom_filter import bf_max_kmers
from pykmhelpers.core.build_params import auto_params, params_for_partitions
from pykmhelpers.pipeline.index_db import IndexDefinition
from pykmhelpers.pipeline.index_ops.layout import LayoutStore
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

    ``partitions`` and ``minim_size`` are index invariants: indexes are only
    mergeable when they share them, so they come from the layout once
    resolved. ``chunk_size`` is set when the open-files ceiling can't fit
    every sample in one kmtricks build; the build is then split into chunks
    of at most that many samples, which are merged.
    """

    threads: int
    partitions: int
    chunk_size: Optional[int] = None
    minim_size: int = 10


def resolve_minim_size(config: IndexOpsConfig, layout: LayoutStore) -> int:
    """Minimizer size of the index: the layout's, else the configured one."""
    stored = layout.minim_size()
    if stored is None:
        layout.set_minim_size(config.minimizer_length)
        return config.minimizer_length
    if stored != config.minimizer_length:
        logger.warning(
            f"Ignoring --minim-size {config.minimizer_length}: this index is "
            f"built with {stored} (from the layout)"
        )
    return stored


def resolve_partitions(
    i: IndexDefinition, sample_count: int, config: IndexOpsConfig, layout: LayoutStore
) -> int:
    """Partition count of the span holding ``i``, fixed for the index's life.

    Taken from the layout, else from the definition (``compose -p``), else
    sized from the resource limits for a full shard and stored in the layout.
    """
    stored = layout.partition_count(i.span) or i.partition_count
    if stored:
        if config.partition_count and config.partition_count != stored:
            logger.warning(
                f"Ignoring --partition-count {config.partition_count}: span "
                f"{i.span} is built with {stored} partitions (mergeable indexes "
                f"must share it)"
            )
        return clamp_partitions(stored)

    if config.partition_count:
        partitions = clamp_partitions(config.partition_count)
    else:
        # Sized for a full shard so the value holds as the index grows
        samples = layout.sample_budget(i.span) or sample_count
        params = auto_params(
            kmers=bf_max_kmers(i.bf_size, i.fp_rate),
            samples=max(1, samples),
            limits=config.limits or "{}",
            safety_margin=config.safety_margin,
        )
        if params.partitions is None:
            raise TypeError("expected auto_params() to set partitions")
        partitions = clamp_partitions(params.partitions)

    layout.set_partition_count(i.span, partitions)
    logger.info(f"  └── Span {i.span} sized to {partitions} partitions")
    return partitions


def resolve_build_params(
    i: IndexDefinition,
    sample_count: int,
    config: IndexOpsConfig,
    layout: LayoutStore,
) -> BuildParams:
    """Resolve the build parameters of index ``i`` holding ``sample_count`` samples.

    The partition count and the minimizer size are index invariants (see
    ``resolve_partitions``). Threads and chunking are per run: threads are
    the most that fit RAM at that partition count, unless
    ``config.kmindex_threads`` sets them, and chunking follows the open-files
    ceiling.
    """
    minim_size = resolve_minim_size(config, layout)
    partitions = resolve_partitions(i, sample_count, config, layout)

    if config.kmindex_threads:
        return BuildParams(config.kmindex_threads, partitions, None, minim_size)

    params = params_for_partitions(
        kmers=bf_max_kmers(i.bf_size, i.fp_rate),
        samples=sample_count,
        partitions=partitions,
        limits=config.limits or "{}",
        safety_margin=config.safety_margin,
    )
    if params.threads is None or params.samples is None:
        raise TypeError(
            f"expected params_for_partitions() to set threads/samples, got "
            f"threads={params.threads!r}, samples={params.samples!r}"
        )

    chunk_size = params.samples if params.samples < sample_count else None
    if chunk_size is not None:
        logger.info(
            f"  └── '{i.name}' has {sample_count} samples, exceeding the "
            f"{chunk_size} a single kmtricks build can fit under the "
            f"current open-files limit; splitting into chunks"
        )

    logger.info(f"  └── Auto-sized: threads={params.threads}, partitions={partitions}")
    return BuildParams(params.threads, partitions, chunk_size, minim_size)
