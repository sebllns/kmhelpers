import json
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from pykmhelpers.core.bloom_filter import bf_max_kmers
from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.core.build_params import (
    _resolve_limits,
    auto_params,
    params_for_partitions,
    ram_chunk,
)
from pykmhelpers.pipeline.composer import budget_samples_for
from pykmhelpers.pipeline.index_db import IndexDefinition
from pykmhelpers.pipeline.index_ops.layout import LayoutStore
from pykmhelpers.pipeline.index_ops.merging import (
    merge_partitions,
    merge_resources,
    shard_bytes,
)
from pykmhelpers.pipeline.index_ops.types import IndexOpsConfig

logger = logging.getLogger(__name__)

# kmtricks silently raises any lower --nb-partitions value to this floor
KMTRICKS_MIN_PARTITIONS = 4
# Ceiling of an auto-sized partition count
AUTO_MAX_PARTITIONS = 256


def clamp_partitions(count: int) -> int:
    """Apply the kmtricks partition floor; 0 (auto) is left untouched."""
    return max(count, KMTRICKS_MIN_PARTITIONS) if count > 0 else count


def round_auto_partitions(count: int) -> int:
    """Round an auto-sized partition count up to the next power of 2, at most
    ``AUTO_MAX_PARTITIONS``, with the kmtricks floor."""
    count = clamp_partitions(max(count, 1))
    return min(1 << (count - 1).bit_length(), AUTO_MAX_PARTITIONS)


@dataclass(frozen=True)
class BuildParams:
    """Resolved kmindex build parameters for one index.

    ``partitions`` and ``minim_size`` are invariants of a shard: indexes are
    only mergeable when they share them. The minimizer size is fixed at
    design; the partition count by the design (``-p``) or by the first build
    of the shard (see ``resolve_partitions``). ``chunk_size`` is set when the open-files ceiling can't fit
    every sample in one kmtricks build; the build is then split into chunks
    of at most that many samples, which are merged.

    ``partitions_source`` tells where the partition count comes from, for the
    report: ``published`` (the layout records the count of the shard),
    ``design`` (``compose -P``), ``auto`` (sized from the limits),
    ``registered`` (the shard already built) or ``run`` (a run of the session
    already started). It does not take part in comparisons.
    """

    threads: int
    partitions: int
    chunk_size: Optional[int] = None
    minim_size: int = 10
    partitions_source: str = field(default="auto", compare=False)


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


def chunk_samples(
    i: IndexDefinition, config: IndexOpsConfig, layout: LayoutStore
) -> Optional[int]:
    """Most samples one kmtricks chunk of ``i`` holds under ``config.chunk_budget``.

    None when the budget is 0 or without a layout (no span base).
    """
    base = layout.base()
    if not base:
        return None
    return budget_samples_for(i.span, base, config.chunk_budget) or None


def build_kmers(i: IndexDefinition) -> int:
    """k-mers the build of ``i`` holds in memory, for a full shard.

    The Bloom filter capacity counts distinct (solid for raw reads) k-mers;
    kmtricks counts every occurrence before filtering, so it is scaled by the
    shard's k-mer ratio.
    """
    return math.ceil(bf_max_kmers(i.bf_size, i.fp_rate) * i.kmer_ratio)


def partitions_source(
    i: IndexDefinition, layout: LayoutStore, shard: Optional[str] = None
) -> str:
    """``published`` when the layout records the count of ``shard``,
    ``design`` when the partition count of ``i`` is fixed, else ``auto``
    (the tests of ``resolve_partitions``)."""
    if shard and layout.shard_partition_count(shard):
        return "published"
    return "design" if i.partition_count or layout.partition_count(i.span) else "auto"


def resolve_partitions(
    i: IndexDefinition,
    sample_count: int,
    config: IndexOpsConfig,
    layout: LayoutStore,
    shard: Optional[str] = None,
) -> int:
    """Partition count of ``i``, part of ``shard``: the count the layout
    records for the shard once published, else fixed at design
    (``compose -P``), else sized from the resource limits for a full shard.

    A shard already built, or a run of the session already started, keeps its
    own count: ``IndexExecutor.align_with`` applies it afterwards.
    """
    published = layout.shard_partition_count(shard) if shard else None
    if published:
        logger.info(f"  └── Partitions: {clamp_partitions(published)} (published shard)")
        return clamp_partitions(published)

    fixed = i.partition_count or layout.partition_count(i.span)
    if fixed:
        logger.info(f"  └── Partitions: {clamp_partitions(fixed)} (design -P)")
        return clamp_partitions(fixed)

    # Sized for a full shard so the value holds as the index grows
    samples = layout.sample_budget(i.span) or sample_count
    params = auto_params(
        kmers=build_kmers(i),
        samples=max(1, samples),
        limits=config.limits or "{}",
        safety_margin=config.safety_margin,
        # max_chunks applies to the chunks of the plan (resolve_build_params):
        # on a full shard it would only cut the threads partitions are sized for
        max_chunks=None,
        max_chunk_samples=chunk_samples(i, config, layout),
    )
    if params.partitions is None or params.threads is None:
        raise TypeError("expected auto_params() to set partitions and threads")

    partitions = round_auto_partitions(params.partitions)
    if partitions < params.partitions:
        logger.warning(
            f"  └── Auto-sized partition count {params.partitions} capped to "
            f"{AUTO_MAX_PARTITIONS}: fewer threads fit the RAM limit"
        )

    # The merges of the shard: a merge thread maps 1/P of the shard. Raise P for
    # them only when the job is killed on RSS ("merge_ram": "hard")
    merge_limits, merge_cpus = merge_resources(config)
    build_threads = config.kmindex_threads or params.threads
    merge_t = min(build_threads, merge_cpus or build_threads)
    size = shard_bytes(i.bf_size, max(1, samples), getattr(i, "bitw", 0))
    for_merge = merge_partitions(size, merge_t, merge_limits.ram)
    side = "build RAM"
    if for_merge > partitions and not merge_limits.hard_ram:
        logger.warning(
            f"  └── Merges of a full shard ({ByteCounter.auto(size, SizeFormat.BYTE)}) "
            f"would need {for_merge} partitions for {merge_t} thread(s) to keep their "
            f"inputs in RAM: kept {partitions} (soft bound, merges may run up to 1.8x "
            'slower); set "merge_ram": "hard" in --limits to raise it'
        )
    elif for_merge > partitions:
        side = "merge RAM"
        # the superk stage opens P + 1 files at 1 thread: a larger P cannot build
        files = _resolve_limits(config.limits or "{}", config.safety_margin)[1]
        cap = min(AUTO_MAX_PARTITIONS, 1 << max(0, (files - 1).bit_length() - 1))
        partitions = max(partitions, min(round_auto_partitions(for_merge), cap))
        if partitions < for_merge:
            logger.warning(
                f"  └── Merges of a full shard ({ByteCounter.auto(size, SizeFormat.BYTE)}) "
                f"need {for_merge} partitions for {merge_t} thread(s), capped to "
                f"{partitions} (at most {AUTO_MAX_PARTITIONS}, open files {files}): "
                "they will use fewer threads"
            )
    # a floor from the limits ("min_partitions"): more merge threads fit the RAM,
    # and the kmtricks merge stage runs min(T, P) tasks (Logan E-B3: P=16 builds as
    # fast as P=4 on a 15k-sample chunk)
    floor = int(json.loads(config.limits or "{}").get("min_partitions") or 0)
    if floor and partitions < floor:
        partitions = min(round_auto_partitions(floor), AUTO_MAX_PARTITIONS)
        side = "min_partitions"
    logger.info(
        f"  └── Partitions: {partitions} (auto from the {side} limit, "
        f"k-mer ratio {i.kmer_ratio})"
    )
    return partitions


def budget_text(budget: int) -> str:
    """``2**37`` for a power of two, else the number."""
    if budget > 1 and budget & (budget - 1) == 0:
        return f"2**{budget.bit_length() - 1}"
    return f"{budget:,}"


def chunk_bound(
    i: IndexDefinition,
    chunk_size: int,
    sample_count: int,
    config: IndexOpsConfig,
    max_chunk_samples: Optional[int],
    partitions: int,
) -> str:
    """What bounds a kmtricks chunk of ``i`` at ``chunk_size`` samples, for the
    splitting message (``_chunk_size``): the chunk budget, the ``--max-chunks``
    cap raising the chunk, or the merge stage, which holds
    ``min(threads, partitions) * (samples + 1)`` open files and
    ``merge_stage_ram`` of RAM."""
    if max_chunk_samples and chunk_size == max_chunk_samples:
        return (
            f"the chunk budget allows at span {i.span} "
            f"({budget_text(config.chunk_budget)} k-mers, --chunk-budget)"
        )
    ram, files, threads, _ = _resolve_limits(config.limits or "{}", config.safety_margin)
    tasks = max(1, min(threads, partitions))
    by_files = files // tasks - 1
    by_ram = ram_chunk(ram, tasks)
    if config.max_chunks and chunk_size == math.ceil(sample_count / config.max_chunks) \
            and chunk_size > min(by_files, by_ram):
        return f"--max-chunks {config.max_chunks} asks for"
    if chunk_size == by_ram and by_ram < by_files:
        return (
            f"the merge-stage RAM allows ({ByteCounter.auto(ram, SizeFormat.BYTE)} for "
            f"{tasks} merge tasks, min({threads} threads, {partitions} partitions): "
            "each holds 169 KiB per open sample)"
        )
    return (
        f"the open-files limit allows ({files} files for {tasks} merge tasks, "
        f"min({threads} threads, {partitions} partitions): "
        "the merge stage opens min(threads, partitions) x (samples + 1))"
    )


def resolve_build_params(
    i: IndexDefinition,
    sample_count: int,
    config: IndexOpsConfig,
    layout: LayoutStore,
    shard: Optional[str] = None,
) -> BuildParams:
    """Resolve the build parameters of index ``i`` holding ``sample_count`` samples,
    a part of ``shard`` (its partition count may be recorded in the layout).

    The partition count and the minimizer size are index invariants (see
    ``resolve_partitions``). Threads and chunking are per run: threads are
    the most that fit RAM at that partition count, unless
    ``config.kmindex_threads`` sets them, and chunking follows the open-files
    ceiling, ``config.max_chunks`` and ``config.chunk_budget``.
    """
    minim_size = resolve_minim_size(i, layout)
    source = partitions_source(i, layout, shard)
    partitions = resolve_partitions(i, sample_count, config, layout, shard)

    max_chunk_samples = chunk_samples(i, config, layout)
    if config.kmindex_threads:
        # Explicit threads skip the limits, but not the chunk budget
        chunk_size = (
            max_chunk_samples
            if max_chunk_samples and max_chunk_samples < sample_count
            else None
        )
        return BuildParams(
            config.kmindex_threads, partitions, chunk_size, minim_size, source
        )

    params = params_for_partitions(
        kmers=build_kmers(i),
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
            f"{chunk_size} {chunk_bound(i, chunk_size, sample_count, config, max_chunk_samples, partitions)}; "
            f"splitting into {math.ceil(sample_count / chunk_size)} chunks"
        )

    logger.info(f"  └── Auto-sized: threads={params.threads}, partitions={partitions}")
    return BuildParams(params.threads, partitions, chunk_size, minim_size, source)
