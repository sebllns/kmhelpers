"""Compose command: build index definition file(s) from lists of samples."""

import click

from pykmhelpers.cli.shared import force_verbose_mode
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.composer import compose_indices, parse_span_list


@click.command(name="compose")
@click.argument("input_files", nargs=1, required=True, type=click.Path(exists=True))
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory for compressed index",
)
@click.option(
    "--prefix",
    default="span",
    help="🏷️   Prefix for index names",
)
@click.option(
    "--name",
    "-n",
    default="index",
    help="🏷️   Name of created index database",
)
@click.option(
    "--span-list",
    "-s",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    required=False,
    help="📋  Allowlist of permitted span IDs (space-separated). Samples assigned to a span not in the list are promoted to the next allowed span.",
)
@click.option(
    "--partition-count",
    "-p",
    type=int,
    default=0,
    help="💾   Desired number of partitions per index, 0 for automatic count (default: 0)",
)
@click.option(
    "--split-size",
    "-b",
    "bf_max_size",
    help="💾  Maximum run size (e.g., '10GB', '5000MB') before splitting samples across indices (default = no limit)",
)
@click.option(
    "--partition-min-size",
    "-m",
    help="💾  Minimum partition file size (e.g., '500MB', '1GB'). If not met, partition count will decrease to maintain this size limit per partition (default = no limit)",
)
@click.option(
    "--partition-count-limit",
    "-P",
    type=int,
    default=256,
    help="⚙️   Partition count limit for auto-partitioning (default: 256)",
)
def compose(
    input_files,
    output_dir,
    prefix,
    name,
    span_list,
    partition_count,
    bf_max_size,
    partition_min_size,
    no_merge,
    exact_partition_count,
    partition_count_limit,
):
    """Compose index definition file(s) from list(s) of samples.

    Examples:

      \b
      kmhelpers compose -o ./db -k 31 samples.yaml

      \b
      kmhelpers compose -o ./db --min_span 25 --max_span 38 --split samples.yaml

      \b
      kmhelpers compose -o ./db --format json samples.yaml

      \b
      kmhelpers compose -o ./db --format yaml --split samples.yaml

      \b
      kmhelpers compose -o ./db -p 0.01 samples.yaml

      \b
      kmhelpers compose -o ./db --partition-count 4 samples.yaml

      \b
      kmhelpers compose -o ./db --recount samples.yaml
    """

    try:
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

        allowed_spans = None
        if span_list:
            try:
                allowed_spans = parse_span_list(span_list)
            except ValueError as e:
                raise click.BadParameter(str(e))

        compose_indices(
            input_files=input_files,
            output_dir=output_dir,
            prefix=prefix,
            name=name,
            allowed_spans=allowed_spans,
            partition_count=partition_count,
            bf_max_size=bf_max_size,
            partition_min_size=partition_min_size,
            no_merge=no_merge,
            exact_partition_count=exact_partition_count,
            partition_count_limit=partition_count_limit,
        )

    except click.BadParameter:
        raise
    except Exception as e:
        raise click.ClickException(f"Compose failed: {e}")
