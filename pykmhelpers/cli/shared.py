"""Shared utilities for CLI commands."""

import json
import logging
from typing import Any

import click
import yaml

from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.core.constants import (
    AUTO_GROUP_MAX,
    AUTO_GROUP_MIN_GAIN,
    AUTO_GROUP_SAMPLES,
    MAX_CHUNKS,
)
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_ops.sources import resolve_input


def parse_size(value: str, what: str) -> int:
    """Parse a size such as '4GB' or '0' into bytes."""
    if str(value).strip() == "0":
        return 0
    try:
        return int(ByteCounter.from_str(value).byte_count)
    except ValueError:
        raise click.BadParameter(f"Invalid size for {what}: {value} (e.g. '4GB', '500MB')")


def parse_shard_size(value: str | None) -> int:
    """Parse a shard size such as '10GB' into bytes; 0 when not set."""
    if not value:
        return 0
    try:
        return int(ByteCounter.from_str(value).byte_count)
    except ValueError:
        raise click.BadParameter(
            f"Invalid shard size: {value} (use a format like '10GB' or '500MB')"
        )


def parse_budget(value: str | None) -> int | None:
    """Parse a budget such as '137438953472', '2**37' or '2^37'; None when not set."""
    if value is None:
        return None
    try:
        base, _, exp = value.replace("^", "**").partition("**")
        result = int(base) ** int(exp) if exp else int(base)
    except ValueError:
        raise click.BadParameter(
            f"Invalid budget: {value} (use a format like '2**37', 0 for no limit)"
        )
    if result < 0:
        raise click.BadParameter(f"Budget must not be negative: {value}")
    return result


def parse_shard_rule(
    shard_budget: str | None, shard_budget_bytes: str | None
) -> tuple[int | None, int]:
    """``(shard_budget, shard_size)`` of `design`/`compose`: one rule at most."""
    if shard_budget is not None and shard_budget_bytes:
        raise click.UsageError(
            "--shard-budget and --shard-budget-bytes cannot be combined"
        )
    return parse_budget(shard_budget), parse_shard_size(shard_budget_bytes)


def sharding_options(f):
    """Shard rule options of `design` and `compose`."""
    f = click.option(
        "--shard-budget-bytes",
        "shard_budget_bytes",
        hidden=True,
        help="💾  Cap a shard by its size on disk (e.g., '256GB', '500000MB') "
        "rather than by --shard-budget: when set, --shard-budget is not used. "
        "Cannot be combined with --shard-budget. Recorded in the layout; passing "
        "it on an update re-shards the layout.",
    )(f)
    f = click.option(
        "--shard-budget",
        "--sb",
        "shard_budget",
        help="💾  Shard budget: a span s is split into shards of at most "
        "ceil8(budget / base**s) samples (about k-mers x samples). 0 for no "
        "limit. Recorded in the layout; passing it on an update re-shards the "
        "layout. [default: '2**43' for a new index]",
    )(f)
    return f


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


def split_names(values) -> list[str] | None:
    """Names or patterns of a repeatable option: --shard a --shard b, or --shard a,b.

    None when the option is not given.
    """
    names = [n for entry in values or () for n in entry.split(",") if n]
    return names or None


def select_shards(registry, values) -> list[str]:
    """Registry shards matching --shard names or glob patterns; all when not given."""
    try:
        return registry.select_indices(split_names(values))
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint="--shard")


no_copy_list_option = click.option(
    "--no-copy-list",
    "--ncl",
    "no_copy_list",
    is_flag=True,
    default=False,
    help="🚩  Point the index definition files to the input sample list instead "
    "of copying it into the compose output folder. The list must then stay in "
    "place and unchanged as it is used for building.",
)


kmer_ratio_option = click.option(
    "--kmer-ratio",
    "--kr",
    "kmer_ratio",
    type=click.FloatRange(min=0, min_open=True),
    default=1.0,
    show_default=True,
    help="⚙   Multiply the k-mer ratio (k-mer occurrences per counted k-mer) that "
    "sizes the build memory. Computed per shard from the sample list (kmer_total), "
    "else 1 for assembled data and 4 for raw reads. Raise it for deep raw reads "
    "listed without kmer_total.",
)

output_dir_option = click.option(
    "--output-dir",
    "-o",
    "work_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Index directory (BUILD_DIR): receives the built index, reused across builds and passed to `query -r`.",
)

_session_option = click.option(
    "--session",
    "-s",
    "session",
    required=False,
    help="⚙   Session to build when INPUT is a directory (default: the last one composed).",
)
_base_path_option = click.option(
    "--bp",
    "--base-path",
    "base_path",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to resolve relative sample paths. By default, relative "
    "paths are resolved from the run directory; use this option if you "
    "need to resolve them from a different location.",
)
_index_ids_option = click.option(
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    required=False,
    help="⚙   Shards to plan, as names or glob patterns (repeatable or "
    "comma-separated: --shard idx_g0_p1, --shard 'idx_g0_*'). A part name "
    "(<shard>_<session>) plans that part as its own index.",
)
_task_option = click.option(
    "--task",
    "task_ids",
    multiple=True,
    required=False,
    help="⚙   Run only what matches these names or glob patterns (repeatable or "
    "comma-separated): a shard or its task (<shard>_<session>) runs all its "
    "jobs; a job runs alone: '<shard>_j<k>' (some chunks, see `plan "
    "--chunks-per-job`) or '<shard>_merge'. E.g. 'idx_g0_*', '*_merge'.",
)
pending_option = click.option(
    "--pending",
    is_flag=True,
    help="🚩  Print the jobs of the plan not done yet, one per line, and run nothing.",
)
cluster_option = click.option(
    "--cluster",
    "--hpc",
    "cluster_file",
    required=False,
    type=click.Path(exists=True, dir_okay=False),
    help="📁  YAML file of the scheduler and the resources of each kind of job "
    "(type: slurm). Sizes the plan from these resources (not with --limits) and "
    "writes BUILD_DIR/assets/SESSION/slurm/, with submit.sh.",
)
chunks_per_job_option = click.option(
    "--chunks-per-job",
    "--cpj",
    "chunks_per_job",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="⚙   Chunks of a shard one job builds: 0 for one job per shard (its "
    "chunks, then its merge); else jobs '<shard>_j<k>' of up to N chunks, then "
    "a job '<shard>_merge'.",
)
_threads_option = click.option(
    "--threads",
    type=int,
    required=False,
    hidden=True,
    help="⚙   Force the number of kmtricks threads instead of sizing them from "
    "--limits.",
)
_limits_option = click.option(
    "--limits",
    metavar="JSON",
    required=False,
    help="⚙   JSON line of resource limits used to auto-size threads/partitions "
    'when --threads is not set, e.g. \'{"ram": 8000000000, "files": 4096, "threads": 8}\'. '
    '"maps" (vm.max_map_count) also bounds the inputs of one merge. '
    "Keys omitted from the JSON are auto-detected from the system.",
)
_safety_margin_option = click.option(
    "--safety-margin",
    type=float,
    default=0.9,
    show_default=True,
    help="⚙   Fraction of a detected system limit to use for any key missing from --limits.",
)
# Not part of _INDEX_LIMITS_OPTIONS: the chunk of a shard depends on its span,
# which `test auto-params` does not have
chunk_budget_option = click.option(
    "--chunk-budget",
    "--cb",
    "chunk_budget",
    default="2**37",
    show_default=True,
    callback=lambda ctx, param, value: parse_budget(value),
    help="⚙   K-mer budget of one kmtricks chunk: a chunk of span s holds at most "
    "ceil8(budget / base**s) samples. 0 for no limit.",
)
_max_chunks_option = click.option(
    "--max-chunks",
    type=click.IntRange(min=0),
    default=MAX_CHUNKS,
    show_default=True,
    help="⚙   Max number of chunks a shard is built in. Bigger chunks mean "
    "fewer build/merge passes but fewer threads. Use 0 to disable the cap.",
)
_skip_compression_option = click.option(
    "--skip-compression",
    "--ncp",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Skip compression of intermediate files during index building (useful on slow disks).",
)
_show_progress_option = click.option(
    "--show-progress",
    "--sp",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Enable animation that shows the current subindex being built (use in an interactive shell).",
)
# Not part of _INDEX_BUILD_OPTIONS: `build` hardcodes fail-on-error, while
# `plan`/`apply` expose this flag individually via @shared.fail_fast_option.
fail_fast_option = click.option(
    "--fail-fast",
    "-x",
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
_keep_previous_option = click.option(
    "--keep-previous",
    is_flag=True,
    default=False,
    help="🚩  Keep the replaced version of an updated index in "
    "BUILD_DIR/work/SESSION/previous/ instead of deleting it.",
)

# Where the plan is (plan, apply, build)
_INDEX_TARGET_OPTIONS = [
    output_dir_option,
    _session_option,
]

# Decisions of the plan (plan, build); `apply` runs the plan as it is
_INDEX_BUILD_OPTIONS = [
    _base_path_option,
    _threads_option,
    _skip_compression_option,
    _keep_previous_option,
    chunks_per_job_option,
]

# Only meaningful for commands that execute a plan (apply, build)
_INDEX_APPLY_OPTIONS = [
    _show_progress_option,
    _notify_option,
]

# For commands that auto-size threads/partitions (plan, build).
_INDEX_LIMITS_OPTIONS = [
    _limits_option,
    _safety_margin_option,
    _max_chunks_option,
]


# Tune the automatic group count of `-g 0`: shown by `profile`, hidden by
# `design` (env vars and -C only, to keep it simple)
_AUTO_GROUP_OPTIONS = [
    (
        "--auto-group-samples",
        dict(
            type=click.IntRange(min=1),
            default=AUTO_GROUP_SAMPLES,
            envvar="KMHELPERS_AUTO_GROUP_SAMPLES",
            help="⚙   With -g 0: start from one group per this many samples.",
        ),
    ),
    (
        "--auto-group-max",
        dict(
            type=click.IntRange(min=1),
            default=AUTO_GROUP_MAX,
            envvar="KMHELPERS_AUTO_GROUP_MAX",
            help="⚙   With -g 0: the most groups.",
        ),
    ),
    (
        "--auto-group-min-gain",
        dict(
            type=click.FloatRange(0, 1),
            default=AUTO_GROUP_MIN_GAIN,
            envvar="KMHELPERS_AUTO_GROUP_MIN_GAIN",
            help="⚙   With -g 0: storage fraction a further group must save to be added.",
        ),
    ),
    (
        "--auto-group-single-max",
        dict(
            metavar="SIZE",
            default=None,
            envvar="KMHELPERS_AUTO_GROUP_SINGLE_MAX",
            callback=lambda ctx, param, value: (
                None if value is None else parse_size(value, "--auto-group-single-max")
            ),
            help="⚙   With -g 0: keep one group when it takes at most SIZE (e.g. 4GB); "
            "0 for no such size. profile: no size by default, compared with its "
            "presence/absence sizes. design: 4GB of built index by default, i.e. "
            "4GB / bitw of profile size.",
        ),
    ),
]

no_grouping_option = click.option(
    "--no-grouping",
    "--ngp",
    "no_grouping",
    is_flag=True,
    help="🚩  One group, no grouping strategy: every sample gets the Bloom filter "
    "of the largest one. Not with -g N.",
)


def auto_group_options(f=None, *, hidden: bool = False):
    """Options tuning the automatic group count of `-g 0`.

    `profile` shows them; `design` passes ``hidden=True`` so they are only
    read from their environment variables (or -C), not listed in its help.
    """

    def decorate(f):
        for name, kwargs in reversed(_AUTO_GROUP_OPTIONS):
            f = click.option(
                name, show_default=True, show_envvar=True, hidden=hidden, **kwargs
            )(f)
        return f

    return decorate(f) if f is not None else decorate


def resolve_definition(input_path: str, session: str | None) -> str:
    """Definition file for INPUT of plan/apply/build (a file or a directory)."""
    try:
        return resolve_input(input_path, session)
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))


def index_target_options(f):
    """BUILD_DIR and session (plan, apply, build)."""
    for opt in reversed(_INDEX_TARGET_OPTIONS):
        f = opt(f)
    return f


def index_build_options(f):
    """Options taking the decisions of a plan (plan, build), not `apply`."""
    for opt in reversed(_INDEX_BUILD_OPTIONS):
        f = opt(f)
    return f


def shard_option(f):
    """--shard: the shards to plan (plan)."""
    return _index_ids_option(f)


def task_option(f):
    """--task: the shards, tasks or jobs of the plan to run (apply)."""
    return _task_option(f)


def index_apply_options(f):
    """Extra options for commands that execute a plan (apply, build), not `plan`."""
    for opt in reversed(_INDEX_APPLY_OPTIONS):
        f = opt(f)
    return f


def index_limits_options(f):
    """Resource limits sizing a plan (plan, build), not `apply`."""
    for opt in reversed(_INDEX_LIMITS_OPTIONS):
        f = opt(f)
    return f


def estimate_build_size(
    fof_path: str, bloom_size: int, bitw: int | None = None
) -> dict:
    """
    Estimate the size required for building an index.

    Simple calculation: index_size_bytes = nb_samples * bloom_size * bitw / 8

    Args:
        fof_path: Path to the FOF file
        bloom_size: Bloom filter size, in bits (cells for an abundance index)
        bitw: Bits per cell of an abundance index, None for presence/absence

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

    # Estimate index size: nb_samples * bloom_size bits (bitw bits per cell)
    index_size_bytes = nb_samples * bloom_size * max(bitw or 0, 1) // 8

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
