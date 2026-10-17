"""Sizing of ``kmindex merge``: threads, inputs per merge, memory footprint, merge tree.

Model (kmindex 0.7.1, measured on Vista, see the merge RAM report):

* Each partition task mmaps the whole partition file of every input
  (``lib/src/index/merge.cpp:145-159``), ``min(T, P)`` tasks at a time: file-backed
  page cache, reclaimable, about ``0.9 * T_eff / P`` of the input size at the peak.
* ``kmindex merge`` loads the repartition table (``uint16[4^m]``) of every sub-index
  registered in the global index it runs in (``lib/src/index/index.cpp:22-47``,
  ``index_infos.cpp:73-74``): anonymous memory ``R * 2 * 4^m``, whatever is merged.
* One output row buffer per partition (``merge.cpp:199``): negligible.

So a merge is bounded by the anonymous memory of its registry, by the number of
mmaps (``vm.max_map_count``) and by the open-file limit, not by the mapped inputs.
"""

import json
import logging
import math
from dataclasses import dataclass

from pykmhelpers.core.build_params import _resolve_limits

logger = logging.getLogger(__name__)

HEADER_BYTES = 49  # .cmbf header
MAPPED_FRACTION = 0.9  # resident share of the mapped inputs at the peak (measured)
MAP_MARGIN = 1000  # mmaps used by the binary and its libraries
DEFAULT_MAX_MAPS = 65530  # Linux default vm.max_map_count
MAX_MAP_COUNT_PATH = "/proc/sys/vm/max_map_count"


def merge_threads(threads: int, partitions: int) -> int:
    """Threads worth giving ``kmindex merge``: it runs one task per partition."""
    return max(1, min(threads, partitions) if partitions > 0 else threads)


def repartition_bytes(minim_size: int) -> int:
    """Anonymous memory of one registered sub-index: its ``uint16[4^m]`` table."""
    return int(2 * 4**minim_size)


def _system_max_maps() -> int:
    try:
        with open(MAX_MAP_COUNT_PATH) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return DEFAULT_MAX_MAPS


@dataclass(frozen=True)
class MergeLimits:
    """Resources one ``kmindex merge`` may use."""

    ram: int
    files: int
    maps: int

    @classmethod
    def resolve(cls, limits: str | None, safety_margin: float = 1.0) -> "MergeLimits":
        """Read ``ram``, ``files`` and ``maps`` from the ``--limits`` JSON line.

        Missing keys fall back to the system values, like the build limits:
        ``maps`` is ``vm.max_map_count`` of this machine (65530 if unreadable).
        """
        ram, files, _, _ = _resolve_limits(limits or "{}", safety_margin)
        maps = json.loads(limits or "{}").get("maps")
        return cls(int(ram), int(files), int(maps or _system_max_maps()))


def max_inputs(
    limits: MergeLimits, partitions: int, minim_size: int, threads: int
) -> tuple[int, str]:
    """Most inputs one merge can take, and the limit that sets it.

    The merge runs in a registry holding only its inputs, so ``k`` inputs cost
    ``k * 2 * 4^m`` of anonymous memory, ``T_eff * k`` mmaps and
    ``T_eff * (k + 1)`` open files.
    """
    t_eff = merge_threads(threads, partitions)
    bounds = {
        "anonymous RAM": limits.ram // repartition_bytes(minim_size),
        "vm.max_map_count": (limits.maps - MAP_MARGIN) // t_eff,
        "open files": limits.files // t_eff - 1,
    }
    name = min(bounds, key=lambda b: bounds[b])
    k = bounds[name]
    if k < 2:
        raise ValueError(
            f"a merge cannot take 2 inputs under the {name} limit "
            f"(ram={limits.ram}, files={limits.files}, maps={limits.maps}, "
            f"threads={t_eff}, minimizer size={minim_size})"
        )
    return k, name


def footprint(
    input_samples: list[int],
    registered: int,
    partitions: int,
    minim_size: int,
    bf_size: int,
    threads: int,
    bw: int = 1,
) -> dict[str, int]:
    """Expected memory of one merge, in bytes.

    ``anon`` must fit in RAM. ``mapped`` is page cache: when it exceeds RAM the
    kernel reclaims it during the merge.
    """
    t_eff = merge_threads(threads, partitions)
    rows = bf_size // partitions if partitions else bf_size
    inputs = sum(
        partitions * (HEADER_BYTES + rows * math.ceil(s * bw / 8))
        for s in input_samples
    )
    anon = registered * repartition_bytes(minim_size) + partitions * math.ceil(
        sum(input_samples) * bw / 8
    )
    mapped = int(MAPPED_FRACTION * t_eff / max(partitions, 1) * inputs)
    return {"anon": anon, "mapped": mapped}


@dataclass(frozen=True)
class MergeStep:
    """One ``kmindex merge``: ``inputs`` into ``name``, in a registry of its own."""

    name: str
    inputs: list[str]
    level: int


def merge_tree(target: str, inputs: list[str], k: int) -> list[MergeStep]:
    """Merges turning ``inputs`` into ``target``, at most ``k`` inputs each.

    Each level splits its inputs into ``ceil(n / k)`` groups of near-equal size;
    intermediate results are named ``{target}__sub{level}_{i}``. The last step
    always produces ``target``. Steps are listed level by level.
    """
    if k < 2:
        raise ValueError(f"a merge needs at least 2 inputs per step, got k={k}")
    if not inputs:
        raise ValueError("nothing to merge")

    steps: list[MergeStep] = []
    current = list(inputs)
    level = 1
    while len(current) > k:
        n_groups = math.ceil(len(current) / k)
        size, extra = divmod(len(current), n_groups)
        groups, start = [], 0
        for g in range(n_groups):
            end = start + size + (1 if g < extra else 0)
            groups.append(current[start:end])
            start = end
        names = []
        for g, group in enumerate(groups):
            if len(group) == 1:  # nothing to merge: moves up unchanged
                names.append(group[0])
                continue
            name = f"{target}__sub{level}_{g}"
            steps.append(MergeStep(name, group, level))
            names.append(name)
        current = names
        level += 1
    steps.append(MergeStep(target, current, level))
    return steps
