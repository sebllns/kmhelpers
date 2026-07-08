"""Path helpers for kmindex index/registry directory layout."""

import os

from pykmhelpers.core.utils import Toolbox


def get_matrix_dir(index_path: str) -> str:
    """
    Get the path to the matrices directory within an index.

    Args:
        index_path: Path to the index directory

    Returns:
        Canonical path to the matrices directory
    """
    return Toolbox.get_canonical_path(os.path.join(index_path, "matrices"))


def get_matrix_path(index_path: str, partition: int, is_compressed: bool = False) -> str:
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