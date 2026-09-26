"""kmtricks build-parameter selection from hardware limits."""

import json
import logging
import math

from pykmhelpers.core.resources import (
    get_available_ram,
    get_available_threads,
    get_max_open_files,
)
from pykmhelpers.vendor import kmparams

logger = logging.getLogger(__name__)


def _chunk_size(
    samples: int, ulimit: int, n_threads: int, max_chunks: int | None
) -> int:
    """Per-chunk sample count.

    Base value: the largest chunk that still fits ``n_threads`` in the merge
    stage (``n_threads * (chunk + 1) <= ulimit``), capped at the total sample
    count and floored at 1.

    With ``max_chunks``, the chunk is raised to ``ceil(samples / max_chunks)``
    so the build is split into at most that many chunks. The merge stage needs
    ``threads * (chunk + 1)`` open files, so a bigger chunk costs threads,
    never RAM (``samples`` does not enter the memory model). ``ulimit - 1`` is
    the largest chunk available at all (one merge thread): a cap that would
    need more than that cannot be honoured, and we warn and stay at that
    ceiling rather than fail.
    """
    chunk_s = max(1, min(ulimit // n_threads - 1, samples))
    if max_chunks is None or max_chunks < 1:
        return chunk_s

    wanted = math.ceil(samples / max_chunks)
    if wanted <= chunk_s:
        return chunk_s

    feasible = max(1, min(ulimit - 1, samples))
    if wanted > feasible:
        logger.warning(
            f"max_chunks={max_chunks} needs {wanted} samples per chunk, but ulimit "
            f"{ulimit} allows at most {feasible} (would need ulimit >= {wanted + 1}); "
            f"using {feasible}, i.e. {math.ceil(samples / feasible)} chunks"
        )
        return feasible
    return wanted


def get_best_params(
    kmers: int,
    ram: int,
    samples: int,
    ulimit: int,
    n_threads: int,
    focus: float = 0.5,
    max_chunks: int | None = None,
) -> kmparams.kmtricks_params:
    """Maximize threads (up to n_threads), then minimize partitions.

    The ideal kmtricks configuration for fixed hardware: use as many threads
    as possible without exceeding ``n_threads`` OR the resource ceilings, and
    for that thread count take the fewest partitions.

    ``samples`` is the TOTAL sample count of the dataset, which may exceed
    what a single kmtricks build can fit under ``ulimit``. When it does, the
    returned params describe one CHUNK, intended for a split build/merge
    workflow: build one sub-index per chunk of ``ceil(samples / p.samples)``
    samples, then merge the sub-indexes. ``p.samples`` on the returned params
    is the per-chunk count, not the original ``samples`` argument.

    The chunk size comes from `_chunk_size`: the largest that fits
    ``n_threads`` in the merge stage, or a bigger one when ``max_chunks``
    caps the number of chunks, which lowers the thread ceiling in exchange.

    The objective is lexicographic but conflict-free:
      * threads is capped by n_threads, by RAM (via the partitions needed),
        and by ulimit (merge stage = threads*(samples+1), superk stage =
        threads*partitions + writers).
      * for the chosen thread count, ``nb_partitions()`` returns the RAM
        MINIMUM, which is also the best case for the superk file count.

    So this returns the largest feasible thread count with its minimum
    partitions. Raises ValueError if not even one thread fits ``ulimit``.
    """
    logger.debug(
        f"get_best_params: kmers={kmers}, ram={ram}, samples={samples}, "
        f"ulimit={ulimit}, n_threads={n_threads}, focus={focus}, "
        f"max_chunks={max_chunks}"
    )

    if ulimit < 1:
        raise ValueError(f"ulimit {ulimit} too low: at least 1 open file required")

    chunk_s = _chunk_size(samples, ulimit, n_threads, max_chunks)

    # hard ceiling on threads: user cap and the merge-stage file limit
    max_t = min(n_threads, ulimit // (chunk_s + 1))
    if max_t < 1:
        raise ValueError(
            f"ulimit {ulimit} too low: merge stage needs at least "
            f"{chunk_s + 1} open files for a single thread"
        )

    # walk down from the ceiling; first feasible t is the maximum, and its
    # RAM-minimum partitions is the minimum partition count for that t
    for t in range(max_t, 0, -1):
        p = kmparams.kmtricks_params(
            kmers=kmers, memory=ram, threads=t, samples=chunk_s, focus=focus
        )
        p.nb_partitions()  # minimum partitions for t threads (RAM floor)
        p.nb_open_files()
        if not isinstance(p.files, dict):
            raise TypeError(f"expected nb_open_files() to set a dict, got {p.files!r}")
        if max(p.files.values()) <= ulimit:
            logger.debug(
                f"get_best_params: chosen threads={t}, partitions={p.partitions}, "
                f"samples={chunk_s}, chunks={math.ceil(samples / chunk_s)}, "
                f"files={max(p.files.values())}"
            )
            return p

    raise ValueError("no feasible configuration under the given ulimit")


def params_for_partitions(
    kmers: int,
    samples: int,
    partitions: int,
    limits: str,
    safety_margin: float = 1.0,
    max_chunks: int | None = None,
) -> kmparams.kmtricks_params:
    """Resolve threads and chunk size for a FIXED partition count.

    Indexes can only be merged when they share their partition count, so an
    index keeps the count decided for it once (see the layout). RAM is then
    absorbed by the thread count instead: ``nb_threads`` gives the most
    threads that fit ``ram`` at that partition count, capped by the thread
    limit and by the open-files ceiling of the merge and superk stages.

    ``p.samples`` on the returned params is the per-chunk sample count, as in
    `get_best_params`, and ``max_chunks`` caps the number of chunks the same way.
    """
    ram, ulimit, n_threads, focus = _resolve_limits(limits, safety_margin)
    if partitions < 1:
        raise ValueError(f"partition count {partitions} must be at least 1")
    if ulimit < 1:
        raise ValueError(f"ulimit {ulimit} too low: at least 1 open file required")

    ram_params = kmparams.kmtricks_params(
        kmers=kmers, memory=ram, partitions=partitions, focus=focus
    )
    ram_params.nb_threads()
    if ram_params.threads is None:
        raise TypeError("expected nb_threads() to set threads")

    chunk_s = _chunk_size(samples, ulimit, n_threads, max_chunks)
    max_t = min(n_threads, ram_params.threads, ulimit // (chunk_s + 1))
    if max_t < 1:
        raise ValueError(
            f"ulimit {ulimit} too low: merge stage needs at least "
            f"{chunk_s + 1} open files for a single thread"
        )

    for t in range(max_t, 0, -1):
        p = kmparams.kmtricks_params(
            kmers=kmers,
            memory=ram,
            threads=t,
            samples=chunk_s,
            partitions=partitions,
            focus=focus,
        )
        p.max_memory()
        p.nb_open_files()
        if not isinstance(p.files, dict):
            raise TypeError(f"expected nb_open_files() to set a dict, got {p.files!r}")
        if max(p.files.values()) <= ulimit:
            logger.debug(
                f"params_for_partitions: threads={t}, partitions={partitions}, "
                f"samples={chunk_s}, chunks={math.ceil(samples / chunk_s)}, "
                f"files={max(p.files.values())}"
            )
            return p

    raise ValueError(
        f"no feasible configuration with {partitions} partitions under the given limits"
    )


def _resolve_limits(limits: str, safety_margin: float) -> tuple[int, int, int, float]:
    """Fill the limits missing from ``limits`` with the system's own."""
    parsed = json.loads(limits)

    ram = parsed.get("ram")
    if ram is None:
        ram = get_available_ram(safety_margin)

    ulimit = parsed.get("files")
    if ulimit is None:
        ulimit = get_max_open_files(safety_margin)

    n_threads = parsed.get("threads")
    if n_threads is None:
        n_threads = get_available_threads(safety_margin)

    return ram, ulimit, n_threads, parsed.get("focus", 0.5)


def auto_params(
    kmers: int,
    samples: int,
    limits: str,
    safety_margin: float = 1.0,
    max_chunks: int | None = None,
) -> kmparams.kmtricks_params:
    """Resolve system limits and delegate to `get_best_params`.

    Args:
        kmers: Max number of k-mers across samples.
        samples: Total sample count of the dataset (see `get_best_params`).
        limits: One line of JSON with optional "ram" (bytes), "files"
            (max open files, i.e. ulimit -n), "threads", and "focus" keys.
            Any key that is missing or null falls back to the current
            system limit, scaled down by ``safety_margin``.
        safety_margin: Fraction of a detected system limit to use when the
            corresponding key is absent from ``limits`` (default: 0.9).
        max_chunks: Cap on the number of chunks the dataset is split into.
            None (or < 1) leaves the chunk size to the open-files limit alone.

    Returns:
        kmparams.kmtricks_params: best configuration for the given limits.

    Raises:
        ValueError: if the resolved configuration exceeds one of the limits.
    """
    ram, ulimit, n_threads, focus = _resolve_limits(limits, safety_margin)

    params = get_best_params(
        kmers=kmers,
        ram=ram,
        samples=samples,
        ulimit=ulimit,
        n_threads=n_threads,
        focus=focus,
        max_chunks=max_chunks,
    )

    # sanity check: the chosen configuration must stay within the limits
    if params.threads is None or params.memory is None:
        raise ValueError(f"incomplete configuration: {params}")
    if not isinstance(params.files, dict):
        raise TypeError(f"expected a files dict, got {params.files!r}")
    max_files = max(params.files.values())
    if max_files > ulimit:
        raise ValueError(f"open files {max_files} exceeds limit {ulimit}")
    if params.memory > ram:
        raise ValueError(f"memory {params.memory} exceeds limit {ram}")
    if params.threads > n_threads:
        raise ValueError(f"threads {params.threads} exceeds limit {n_threads}")

    return params
