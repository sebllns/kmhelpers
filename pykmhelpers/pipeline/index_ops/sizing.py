import logging
import math
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

    ``partitions`` and ``minim_size`` are invariants of a shard: indexes are
    only mergeable when they share them. The minimizer size is fixed at
    design; the partition count by the design (``-p``) or by the first build
    of the shard (see ``resolve_partitions``). ``chunk_size`` is set when the open-files ceiling can't fit
    every sample in one kmtricks build; the build is then split into chunks
    of at most that many samples, which are merged.
    """

    threads: int
    partitions: int
    chunk_size: Optional[int] = None
    minim_size: int = 10


def resolve_minim_size(i: IndexDefinition, layout: LayoutStore) -> int:
    """Minimizer size of ``i``, fixed at design: its definition's, else the
    layout's."""
    minim_size = getattr(i, "minim_size", 0) or layout.minim_size()
    if not minim_size:
        raise ValueError(
            f"'{i.name}' has no minimizer size: it is set at design, "
            "redo the design (design/compose --minim-size)"
        )
    return minim_size


def resolve_partitions(
    i: IndexDefinition, sample_count: int, config: IndexOpsConfig, layout: LayoutStore
) -> int:
    """Partition count of ``i``: fixed at design (``compose -p``), else sized
    from the resource limits for a full shard.

    A shard already built, or a run of the session already started, keeps its
    own count: ``IndexExecutor.align_with`` applies it afterwards.
    """
    fixed = i.partition_count or layout.partition_count(i.span)
    if fixed:
        logger.info(f"  └── Partitions: {clamp_partitions(fixed)} (design -p)")
        return clamp_partitions(fixed)

    # Sized for a full shard so the value holds as the index grows
    samples = layout.sample_budget(i.span) or sample_count
    params = auto_params(
        kmers=bf_max_kmers(i.bf_size, i.fp_rate),
        samples=max(1, samples),
        limits=config.limits or "{}",
        safety_margin=config.safety_margin,
        max_chunks=config.max_chunks or None,
        max_chunk_samples=layout.chunk_samples(i.span),
    )
    if params.partitions is None:
        raise TypeError("expected auto_params() to set partitions")
    partitions = clamp_partitions(params.partitions)
    logger.info(f"  └── Partitions: {partitions} (auto from the limits)")
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
    ceiling, ``config.max_chunks`` and the chunk model of the layout.
    """
    minim_size = resolve_minim_size(i, layout)
    partitions = resolve_partitions(i, sample_count, config, layout)

    max_chunk_samples = layout.chunk_samples(i.span)
    if config.kmindex_threads:
        # Explicit threads skip the limits, but not the chunk model
        chunk_size = (
            max_chunk_samples
            if max_chunk_samples and max_chunk_samples < sample_count
            else None
        )
        return BuildParams(config.kmindex_threads, partitions, chunk_size, minim_size)

    params = params_for_partitions(
        kmers=bf_max_kmers(i.bf_size, i.fp_rate),
        samples=sample_count,
        partitions=partitions,
        limits=config.limits or "{}",
        safety_margin=config.safety_margin,
        max_chunks=config.max_chunks or None,
        max_chunk_samples=max_chunk_samples,
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
            f"{chunk_size} a single kmtricks build can fit under the current "
            f"limits; splitting into {math.ceil(sample_count / chunk_size)} chunks"
        )

    logger.info(f"  └── Auto-sized: threads={params.threads}, partitions={partitions}")
    return BuildParams(params.threads, partitions, chunk_size, minim_size)
