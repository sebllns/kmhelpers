"""On-disk shape and format helpers for a kmindex index.

Everything here is about how an index is structured on disk: matrix file
geometry (header/row/byte sizes), parsing the text files kmtricks writes
(options.txt, kmtricks.fof), and validating that the expected directory
structure is present. Path construction lives in :mod:`kmindex_paths`.
"""

import json
import logging
import os
from typing import Any, Dict, List

from pykmhelpers.core.kmindex_paths import get_json_path, get_matrix_path
from pykmhelpers.core.utils import Toolbox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Matrix file geometry
# ---------------------------------------------------------------------------
def get_header_byte_size() -> int:
    """Get the size of the matrix file header (49 bytes)."""
    return 49


def get_bytes_per_row(sample_count: int) -> int:
    """Number of bytes to store one row of bitvectors: ceil(sample_count / 8)."""
    return (sample_count + 7) // 8


def get_row_count(matrix_byte_size: int, row_byte_size: int, header_size: int) -> int:
    """Compute the number of rows in a matrix file."""
    assert matrix_byte_size > 0
    assert row_byte_size > 0
    assert header_size >= 0
    return (matrix_byte_size - header_size) // row_byte_size


def get_file_byte_size(path: str, is_compressed: bool) -> int:
    """Size of a matrix file, adding the .ef sidecar when compressed."""
    return Toolbox.get_size(path) + (
        Toolbox.get_size(path + ".ef") if is_compressed else 0
    )


def get_bytes_per_matrix(
    index_path: str, partition: int, is_compressed: bool = False
) -> int:
    """Byte size of a matrix partition file."""
    return get_file_byte_size(
        get_matrix_path(index_path, partition, is_compressed), is_compressed
    )


# ---------------------------------------------------------------------------
# File parsers
# ---------------------------------------------------------------------------
def load_options_file(file_path: str) -> Dict[str, Any]:
    """Load and parse an options.txt file into a dictionary."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Options file not found: {file_path}")

    with open(file_path, "r") as f:
        content = f.read().strip()

    # Remove "Options: " prefix if present
    if content.startswith("Options: "):
        content = content[9:]

    options: Dict[str, Any] = {}
    for pair in content.split(", "):
        if "=" in pair:
            key, value = pair.split("=", 1)

            if key == "nb_parts":
                key = "nb_partitions"

            if value.isdigit():
                options[key] = int(value)
            elif value.replace(".", "", 1).isdigit():
                options[key] = float(value)
            elif value.lower() in ("true", "false"):
                options[key] = value.lower() == "true"
            else:
                options[key] = value

    return options


def load_fof_file(file_path: str) -> List[str]:
    """Load a kmtricks.fof file and extract sample IDs."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"FOF file not found: {file_path}")

    sample_ids = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and ":" in line:
                sample_ids.append(line.split(":", 1)[0].strip())

    return sample_ids


def index_exists_in_json(json_file_path: str, index_id: str) -> bool:
    """Check whether index_id is registered in the given index.json."""
    with open(json_file_path, "r") as file:
        data = json.load(file)
    return index_id in data["index"]


def create_empty_index_json(output_dir: str) -> str:
    """Create an empty index.json file in the specified output directory."""
    os.makedirs(output_dir, exist_ok=True)

    output_file = get_json_path(output_dir)
    if os.path.exists(output_file):
        return ""

    index_data = {
        "index": {},
        "path": os.path.realpath(Toolbox.get_canonical_path(output_dir)),
    }

    with open(output_file, "w") as f:
        json.dump(index_data, f, indent=4)

    logger.info(f"Created empty index.json at: {output_file}")
    return output_file


# ---------------------------------------------------------------------------
# Structure validation
# ---------------------------------------------------------------------------
def check_index_structure(directory_path, partition_count=256) -> bool:
    """Check the directory has the expected kmindex structure; log missing files."""
    expected_files = {"build_infos.txt", "hash.info", "kmtricks.fof", "options.txt"}
    expected_dirs = {"config_gatb", "matrices", "repartition_gatb"}
    expected_config_files = {"config_gatb/gatb.config"}
    expected_repartition_files = {"repartition_gatb/repartition.minimRepart"}

    expected_matrix_files = {
        f"matrices/matrix_{i}.cmbf" for i in range(partition_count)
    }

    all_expected = (
        expected_files
        | expected_dirs
        | expected_config_files
        | expected_repartition_files
        | expected_matrix_files
    )

    if not os.path.exists(directory_path):
        logger.error(f"Directory '{directory_path}' does not exist!")
        return False

    logger.info(f"Checking index structure in: {directory_path}")

    missing_items = [
        item
        for item in sorted(all_expected)
        if not os.path.exists(os.path.join(directory_path, item))
    ]

    if missing_items:
        logger.warning(f"MISSING ITEMS ({len(missing_items)}):")
        logger.warning("-" * 30)

        missing_root_files = [
            item for item in missing_items if "/" not in item and "." in item
        ]
        missing_dirs = [
            item for item in missing_items if "/" not in item and "." not in item
        ]
        missing_config = [
            item for item in missing_items if item.startswith("config_gatb/")
        ]
        missing_matrices = [
            item for item in missing_items if item.startswith("matrices/")
        ]
        missing_repartition = [
            item for item in missing_items if item.startswith("repartition_gatb/")
        ]

        if missing_root_files:
            logger.warning("Root files:")
            for item in missing_root_files:
                logger.warning(f"  - {item}")

        if missing_dirs:
            logger.warning("Directories:")
            for item in missing_dirs:
                logger.warning(f"  - {item}/")

        if missing_config:
            logger.warning("Config files:")
            for item in missing_config:
                logger.warning(f"  - {item}")

        if missing_repartition:
            logger.warning("Repartition files:")
            for item in missing_repartition:
                logger.warning(f"  - {item}")

        if missing_matrices:
            logger.warning(f"Matrix files ({len(missing_matrices)}):")
            if len(missing_matrices) > 10:
                for item in missing_matrices[:5]:
                    logger.warning(f"  - {item}")
                logger.warning(f"  ... ({len(missing_matrices) - 10} more)")
                for item in missing_matrices[-5:]:
                    logger.warning(f"  - {item}")
            else:
                for item in missing_matrices:
                    logger.warning(f"  - {item}")

    return not missing_items
