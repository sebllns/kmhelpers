"""Shared utilities for CLI commands."""

import json
import logging
from typing import Any

import yaml

from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.pipeline.fof import FofManager


def deserialize(filename: str) -> Any:
    data = None
    with open(filename, "r") as f:
        if filename.endswith(".json"):
            data = json.load(f)
        elif filename.endswith((".yaml", ".yml")):
            data = yaml.safe_load(f)
        else:
            raise NotImplementedError(f"Unsupported file format")
    return data


def force_verbose_mode():
    root_logger = logging.getLogger()
    if root_logger.getEffectiveLevel() > logging.INFO:
        root_logger.setLevel(logging.INFO)
        # Also update all handlers
        for handler in root_logger.handlers:
            if handler.level > logging.INFO:
                handler.setLevel(logging.INFO)


def parse_range(value: str):
    """Parse interval arguments supporting multiple formats:
    - Single values: '28'
    - Comma-separated: '27,28,29'
    - Range notation: '[27-30]' or '27-30'
    """
    result = []
    # Handle range notation [27-30] or 27-30
    item = value.strip(" []-")
    if "-" in item:
        # Range notation: 27-30
        try:
            start, end = item.split("-")
            result.extend(i for i in range(int(start.strip()), int(end.strip()) + 1))
        except ValueError:
            result.append(item)
    else:
        # Comma-separated or single value
        result.extend(int(s.strip()) for s in item.split(","))
    return result


def parse_multiple_ranges(values: tuple[str]):
    result = []
    for item in values:
        result.extend(parse_range(item))
    return result


def estimate_build_size(
    fof_path: str, bloom_size: int | None = None, nb_cell: int | None = None
) -> dict:
    """
    Estimate the size required for building an index.

    Simple calculation: index_size_bytes = nb_samples * bloom_size

    Args:
        fof_path: Path to the FOF file
        bloom_size: Bloom filter size in bytes (for presence/absence)
        nb_cell: Number of cells in bytes (for abundance counting)

    Returns:
        Dictionary with size estimates
    """
    # Load FOF and count samples
    manager = FofManager()
    samples = manager.load_with_paths(fof_path)
    nb_samples = len(samples)

    # Calculate total input size
    total_input_size = 0
    # total_input_size = sum(
    #     os.path.getsize(path) for path in samples.values() if os.path.isfile(path)
    # )

    # Estimate index size: nb_samples * bloom_size
    if bloom_size is not None:
        index_size_bytes = nb_samples * bloom_size
    elif nb_cell is not None:
        index_size_bytes = nb_samples * nb_cell
    else:
        index_size_bytes = 0

    # Convert to human-readable format
    index_size_obj = ByteCounter.auto(index_size_bytes, SizeFormat.BYTE)
    input_size_obj = ByteCounter.auto(total_input_size, SizeFormat.BYTE)

    return {
        "input_size": total_input_size,
        "input_size_str": str(input_size_obj),
        "sample_count": nb_samples,
        "index_size_min_bytes": index_size_bytes,
        "index_size_min_str": str(index_size_obj),
    }
