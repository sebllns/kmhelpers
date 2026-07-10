"""Pure path/location helpers for the kmindex index/registry directory layout.

These functions only build or test file locations; they depend on nothing
heavier than ``os`` and ``Toolbox``, so any module that just needs a path can
import this without pulling in the index classes.
"""

import os
from typing import Tuple

from pykmhelpers.core.utils import Toolbox


def get_index_path(root: str, index: str) -> str:
    """Get the full path to an index directory."""
    return Toolbox.get_canonical_path(os.path.join(root, index))


def get_path_inside_index(root: str, file: str) -> str:
    """Get the full path to a file within an index directory."""
    return Toolbox.get_canonical_path(os.path.join(root, file))


def get_matrix_dir(index_path: str) -> str:
    """Get the path to the matrices directory within an index."""
    return Toolbox.get_canonical_path(os.path.join(index_path, "matrices"))


def get_matrix_path(
    index_path: str, partition: int, is_compressed: bool = False
) -> str:
    """Get the path to a specific matrix partition file."""
    return os.path.join(
        get_matrix_dir(index_path),
        f"blocks_{partition}" if is_compressed else f"matrix_{partition}.cmbf",
    )


def get_ef_path(index_path: str, partition: int) -> str:
    """Get the path to the Elias-Fano file for a compressed partition."""
    return get_matrix_path(index_path, partition, True) + ".ef"


def get_compressed_files_path(index_path: str, partition: int) -> Tuple[str, str]:
    """Get paths to both compressed matrix files (blocks and .ef)."""
    return (
        get_matrix_path(index_path, partition, True),
        get_ef_path(index_path, partition),
    )


def get_fof_path(root: str) -> str:
    """Get the path to kmtricks.fof file within an index directory."""
    return get_path_inside_index(root, "kmtricks.fof")


def get_options_path(root: str) -> str:
    """Get the path to options.txt file within an index directory."""
    return get_path_inside_index(root, "options.txt")


def get_json_path(root: str) -> str:
    """Get the path to index.json file within a directory."""
    return get_path_inside_index(root, "index.json")


def b_json_exists(root: str) -> bool:
    """Check if index.json exists in the given directory."""
    return os.path.isfile(get_json_path(root))


def b_index_exists(root: str, index: str) -> bool:
    """Check if an index directory exists."""
    return os.path.isdir(get_index_path(root, index))