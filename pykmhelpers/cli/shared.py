"""Shared utilities for CLI commands."""

import os
import yaml
import click
from pykmhelpers.operations.fof import FofManager
from pykmhelpers.operations.byte import ByteCounter, SizeFormat


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


def get_project_config(project_path):
    """Load project configuration from .kmhelpers.yaml"""
    config_path = os.path.join(project_path, ".kmhelpers.yaml")
    if not os.path.exists(config_path):
        raise click.ClickException(
            f"Project not initialized. Run 'kmhelpers project create {project_path}' first"
        )
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise click.ClickException(f"Failed to load project config: {e}")


def save_project_config(project_path, config):
    """Save project configuration to .kmhelpers.yaml"""
    config_path = os.path.join(project_path, ".kmhelpers.yaml")
    try:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        raise click.ClickException(f"Failed to save project config: {e}")
