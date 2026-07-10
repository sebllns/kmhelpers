"""Compose command: build index definition file(s) from lists of samples."""

import datetime
import logging
import os

import click

from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.log import Log
from pykmhelpers.pipeline.composer import IndexComposer

logger = logging.getLogger(__name__)


@click.command(name="compose")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory.",
)
@click.option(
    "--name",
    "-n",
    required=True,
    help="🏷️   Name of created index.",
)
@click.option(
    "--session-id",
    "-S",
    required=False,
    default=lambda: datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
    show_default="current timestamp",
    help="🏷️   Session tag appended to index names.",
)
@click.option(
    "--profiles-file",
    "-pf",
    "profiles_file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    required=False,
    help="📋  YAML profiles file defining span lists and Bloom filter parameters (required to build a new index).",
)
@click.option(
    "--profile",
    "-pr",
    "selected_profile",
    type=str,
    required=False,
    help="⚙️  Profile name to use (default: uses default_profile from the profiles file).",
)
@click.option(
    "--partition-count",
    "-p",
    type=int,
    default=0,
    show_default=True,
    help="💾  Desired number of partitions per index, 0 for automatic count.",
)
@click.option(
    "--split-size",
    "-b",
    "bf_max_size",
    help="💾  Maximum run size (e.g., '10GB', '5000MB') before splitting samples across indices.",
)
@click.option(
    "--partition-min-size",
    "-m",
    help="💾  Minimum partition file size (e.g., '500MB', '1GB'). If not met, partition count will decrease to maintain this size limit per partition.",
)
@click.option(
    "--partition-count-limit",
    "-P",
    type=int,
    default=256,
    show_default=True,
    help="⚙️  Partition count limit for auto-partitioning.",
)
@click.pass_context
def compose(
    ctx,
    input_file,
    output_dir,
    profiles_file,
    selected_profile,
    name,
    partition_count,
    bf_max_size,
    partition_min_size,
    partition_count_limit,
    session_id,
):
    """Compose index definition file(s) from a sample list.

    \b
    Input:  JSONL sample list (from `list`), profiles YAML for new index (from `profile`)
    Output: index definition files in OUTPUT_DIR/NAME/RUN_ID/

    The run directory contains a NAME.yaml registry. Pass
    OUTPUT_DIR/NAME/RUN_ID/NAME.yaml as INPUT_FILE to `plan`, `build` or `apply` to
    process the index.

    Use --profiles-file to build a new index. To update an existing index, omit
    --profiles-file: the layout file at OUTPUT_DIR/NAME_layout.yaml is loaded automatically.

    Examples:

      \b
      kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml

      \b
      kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --profile baseline

      \b
      kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --partition-count 4

      \b
      kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --partition-min-size 500MB

      \b
      kmhelpers compose samples.jsonl -o ./db -n my_index -pf profiles.yaml --split-size 10GB

      \b
      kmhelpers compose samples.jsonl -o ./db -n my_index
    """

    try:
        layout_file = None
        if not profiles_file:
            auto_layout = os.path.join(output_dir, f"{name}_layout.yaml")
            if os.path.isfile(auto_layout):
                layout_file = auto_layout
            else:
                raise click.UsageError(
                    f"No layout file found at {auto_layout}. "
                    "Use --profiles-file to build a new index."
                )
        else:
            auto_layout = os.path.join(output_dir, f"{name}_layout.yaml")
            force = (ctx.obj or {}).get("yes", False)
            if os.path.isfile(auto_layout) and not force:
                if not click.confirm(
                    f"Layout file already exists at {auto_layout}. Overwrite it?",
                    default=False,
                ):
                    raise click.Abort()

        if partition_count < 0:
            raise click.BadParameter(
                f"Constraint must be respected: partition_count >= 0 (got partition_count = {partition_count})"
            )

        try:
            bf_max_size = ByteCounter.from_str(bf_max_size) if bf_max_size else None
        except ValueError:
            raise click.BadParameter(
                f"Invalid bf_max_size format: {bf_max_size} (use format like '1GB', '500MB')"
            )

        try:
            partition_min_size = (
                ByteCounter.from_str(partition_min_size) if partition_min_size else None
            )
        except ValueError:
            raise click.BadParameter(
                f"Invalid partition_min_size format: {partition_min_size} (use format like '1GB', '500MB')"
            )

        IndexComposer(
            profiles_file=profiles_file,
            layout_file=layout_file,
            selected_profile=selected_profile,
            name=name,
            partition_count=partition_count,
            bf_max_size=bf_max_size,
            partition_min_size=partition_min_size,
            no_merge=False,
            exact_partition_count=False,
            partition_count_limit=partition_count_limit,
        ).run(
            input_file=input_file,
            output_dir=output_dir,
            run_id=session_id,
        )
        logger.info("SUCCESS ('compose')")
    except (click.UsageError, click.BadParameter):
        # click renders these with their own message and non-zero exit code.
        raise
    except Exception as e:
        Log.handle_exception(logger=logger, e=e, msg="Compose failed")
        raise click.ClickException("FAILED ('compose')")
