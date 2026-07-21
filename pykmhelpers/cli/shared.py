"""Shared utilities for CLI commands."""

import json
import logging
from typing import Any

import click
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


output_dir_option = click.option(
    "--output-dir",
    "-o",
    "work_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output (working) directory path.",
)

_base_path_option = click.option(
    "--base-path",
    "-b",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to resolve relative sample paths. By default, relative "
    "paths are resolved from the run directory; use this option if you "
    "need to resolve them from a different location.",
)
_span_option = click.option(
    "--span",
    "-s",
    multiple=True,
    required=False,
    help="⚙   Build only selected span (e.g., --span 28, --span 27,28,29, --span 27-30, --span [27-30]).",
)
_index_ids_option = click.option(
    "--name",
    "-n",
    "index_ids",
    multiple=True,
    required=False,
    help="⚙   Index IDs to build. Can be specified multiple times (-n id1 -n id2) or comma-separated (-n id1,id2).",
)
_minim_size_option = click.option(
    "--minim-size",
    type=int,
    required=False,
    help="⚙   Minimizer size (4-15, default: 10).",
)
_threads_option = click.option(
    "--threads",
    "-t",
    type=int,
    required=False,
    help="⚙   Number of threads.",
)
_partition_count_option = click.option(
    "--partition-count",
    "-p",
    type=int,
    required=False,
    help="⚙   Override number of partitions.",
)
_limits_option = click.option(
    "--limits",
    metavar="JSON",
    required=False,
    help="⚙   JSON line of resource limits used to auto-size threads/partitions "
    'when --threads is not set, e.g. \'{"ram": 8000000000, "files": 4096}\'. '
    "Keys omitted from the JSON are auto-detected from the system.",
)
_safety_margin_option = click.option(
    "--safety-margin",
    type=float,
    default=0.9,
    show_default=True,
    help="⚙   Fraction of a detected system limit to use for any key missing from --limits.",
)
_skip_compression_option = click.option(
    "--skip-compression",
    "-NC",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Skip compression of intermediate files during index building (useful on slow disks).",
)
_show_progress_option = click.option(
    "--show-progress",
    "-SP",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Enable animation that shows the current subindex being built (use in an interactive shell).",
)
# Not part of _INDEX_BUILD_OPTIONS: `build` hardcodes fail-on-error, while
# `plan`/`apply` expose this flag individually via @shared.fail_fast_option.
fail_fast_option = click.option(
    "--fail-fast",
    "-X",
    "fail_on_error",
    is_flag=True,
    help="🚩  Abort the entire run if any index fails to build, instead of skipping it and continuing.",
)
_notify_option = click.option(
    "--notify",
    required=False,
    metavar="EMAIL",
    help="📧  Send an email notification on exit (success, failure, or timeout).",
)

_INDEX_BUILD_OPTIONS = [
    output_dir_option,
    _base_path_option,
    _minim_size_option,
    _threads_option,
    _partition_count_option,
    _skip_compression_option,
]

# Only meaningful for commands that operate on an already-composed
# definition/registry file (plan, apply); `build` always processes the
# whole input file, so filtering by name/span doesn't apply there.
_INDEX_FILTER_OPTIONS = [
    _span_option,
    _index_ids_option,
]

# Only meaningful for commands that actually execute a build (apply, build);
# `plan` is a preview/dry-run, so a progress bar or completion notification
# don't apply there.
_INDEX_APPLY_OPTIONS = [
    _show_progress_option,
    _notify_option,
]

# Only meaningful for commands that let threads be auto-sized (plan, apply);
# `build` always relies on system-detected limits, with no override.
_INDEX_LIMITS_OPTIONS = [
    _limits_option,
    _safety_margin_option,
]


def index_build_options(f):
    """Shared options for commands that build k-mer indices (plan, apply, build)."""
    for opt in reversed(_INDEX_BUILD_OPTIONS):
        f = opt(f)
    return f


def index_filter_options(f):
    """Extra options for commands that filter by name/span (plan, apply), not `build`."""
    for opt in reversed(_INDEX_FILTER_OPTIONS):
        f = opt(f)
    return f


def index_apply_options(f):
    """Extra options for commands that execute a build (apply, build), not `plan`."""
    for opt in reversed(_INDEX_APPLY_OPTIONS):
        f = opt(f)
    return f


def index_limits_options(f):
    """Extra options for commands that let resource limits be overridden (plan, apply), not `build`."""
    for opt in reversed(_INDEX_LIMITS_OPTIONS):
        f = opt(f)
    return f


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
