"""kmtricks build-parameter selection from hardware limits."""

import json
import logging

from pykmhelpers.core.system import (
    get_available_ram,
    get_available_threads,
    get_max_open_files,
)
from pykmhelpers.vendor import kmparams

logger = logging.getLogger(__name__)


def get_best_params(
    kmers: int,
    ram: int,
    samples: int,
    ulimit: int,
    n_threads: int,
    focus: float = 0.5,
) -> kmparams.kmtricks_params:
    """Maximize threads (up to n_threads), then minimize partitions.

    The ideal kmtricks configuration for fixed hardware: use as many threads
    as possible without exceeding ``n_threads`` OR the resource ceilings, and
    for that thread count take the fewest partitions.

    ``samples`` is the TOTAL sample count of the dataset, which may exceed
    what a single kmtricks build can fit under ``ulimit``. When it does, the
    returned params describe one CHUNK sized at most ``ulimit`` samples,
    intended for a split build/merge workflow: build one sub-index per chunk
    of ``ceil(samples / p.samples)`` samples, then merge the sub-indexes.
    ``p.samples`` on the returned params is the per-chunk count, not the
    original ``samples`` argument.

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
        f"ulimit={ulimit}, n_threads={n_threads}, focus={focus}"
    )

    max_s = min(ulimit - 1, samples)  # per-chunk sample cap for the split build
    # hard ceiling on threads: user cap and the merge-stage file limit
    max_t = min(n_threads, ulimit // (max_s + 1))
    if max_t < 1:
        raise ValueError(
            f"ulimit {ulimit} too low: merge stage needs {max_s + 1} "
            f"open files for a single thread"
        )

    # walk down from the ceiling; first feasible t is the maximum, and its
    # RAM-minimum partitions is the minimum partition count for that t
    for t in range(max_t, 0, -1):
        p = kmparams.kmtricks_params(
            kmers=kmers, memory=ram, threads=t, samples=max_s, focus=focus
        )
        p.nb_partitions()  # minimum partitions for t threads (RAM floor)
        p.nb_open_files()
        if not isinstance(p.files, dict):
            raise TypeError(f"expected nb_open_files() to set a dict, got {p.files!r}")
        if max(p.files.values()) <= ulimit:
            logger.debug(
                f"get_best_params: chosen threads={t}, partitions={p.partitions}, "
                f"samples={max_s}, files={max(p.files.values())}"
            )
            return p

    raise ValueError("no feasible configuration under the given ulimit")


def auto_params(
    kmers: int, samples: int, limits: str, safety_margin: float = 0.9
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

    Returns:
        kmparams.kmtricks_params: best configuration for the given limits.

    Raises:
        ValueError: if the resolved configuration exceeds one of the limits.
    """
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

    focus = parsed.get("focus", 0.5)

    params = get_best_params(
        kmers=kmers,
        ram=ram,
        samples=samples,
        ulimit=ulimit,
        n_threads=n_threads,
        focus=focus,
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
