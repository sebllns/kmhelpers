"""Path helpers for kmindex index/registry directory layout."""

import os

from pykmhelpers.core.utils import Toolbox
from pykmhelpers.vendor import kmparams


def get_matrix_dir(index_path: str) -> str:
    """
    Get the path to the matrices directory within an index.

    Args:
        index_path: Path to the index directory

    Returns:
        Canonical path to the matrices directory
    """
    return Toolbox.get_canonical_path(os.path.join(index_path, "matrices"))


def get_matrix_path(
    index_path: str, partition: int, is_compressed: bool = False
) -> str:
    """
    Get the path to a specific matrix partition file.

    Args:
        index_path: Path to the index directory
        partition: Partition number
        is_compressed: Whether to get the compressed matrix path (default: False)

    Returns:
        Path to the matrix file (either matrix_N.cmbf or blocks_N for compressed)
    """
    return os.path.join(
        get_matrix_dir(index_path),
        f"blocks_{partition}" if is_compressed else f"matrix_{partition}.cmbf",
    )


def get_index_path(root: str, index: str) -> str:
    """
    Get the full path to an index directory.

    Args:
        root: Root directory containing indices
        index: Index ID or name

    Returns:
        Canonical path to the index directory
    """
    return Toolbox.get_canonical_path(os.path.join(root, index))


def get_path_inside_index(root: str, file: str) -> str:
    """
    Get the full path to a file within an index directory.

    Args:
        root: Index root directory
        file: Relative file path within the index

    Returns:
        Canonical path to the file
    """
    return Toolbox.get_canonical_path(os.path.join(root, file))


def get_options_path(root: str) -> str:
    """Get the path to options.txt file within an index directory."""
    return get_path_inside_index(root, "options.txt")


def get_json_path(root: str) -> str:
    """Get the path to index.json file within a directory."""
    return get_path_inside_index(root, "index.json")


def b_json_exists(root: str) -> bool:
    """
    Check if index.json exists in the given directory.

    Args:
        root: Directory to check

    Returns:
        True if index.json exists
    """
    return os.path.isfile(get_json_path(root))


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

    The objective is lexicographic but conflict-free:
      * threads is capped by n_threads, by RAM (via the partitions needed),
        and by ulimit (merge stage = threads*(samples+1), superk stage =
        threads*partitions + writers).
      * for the chosen thread count, ``nb_partitions()`` returns the RAM
        MINIMUM, which is also the best case for the superk file count.

    So this returns the largest feasible thread count with its minimum
    partitions. Raises ValueError if not even one thread fits ``ulimit``.
    """
    # hard ceiling on threads: user cap and the merge-stage file limit
    max_t = min(n_threads, ulimit // (samples + 1))
    if max_t < 1:
        raise ValueError(
            f"ulimit {ulimit} too low: merge stage needs {samples + 1} "
            f"open files for a single thread"
        )

    # walk down from the ceiling; first feasible t is the maximum, and its
    # RAM-minimum partitions is the minimum partition count for that t
    for t in range(max_t, 0, -1):
        p = kmparams.kmtricks_params(
            kmers=kmers, memory=ram, threads=t, samples=samples, focus=focus
        )
        p.nb_partitions()  # minimum partitions for t threads (RAM floor)
        p.nb_open_files()
        if not isinstance(p.files, dict):
            raise TypeError(f"expected nb_open_files() to set a dict, got {p.files!r}")
        if max(p.files.values()) <= ulimit:
            return p

    raise ValueError("no feasible configuration under the given ulimit")
