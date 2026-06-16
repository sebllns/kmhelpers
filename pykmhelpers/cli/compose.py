"""Compose command: build index definition file(s) from lists of samples."""

import click

from pykmhelpers.cli.shared import force_verbose_mode
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.composer import IndexComposer


@click.command(name="compose")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory for compressed index",
)
@click.option(
    "--session",
    "-s",
    required=False,
    help="🏷️   Session tag appended to index names (default: timestamp if not given)",
)
@click.option(
    "--name",
    "-n",
    default="index",
    help="🏷️   Name of created index database",
)
@click.option(
    "--profiles-file",
    "-pf",
    "profiles_file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    required=False,
    help="📋  YAML profiles file defining span lists and Bloom filter parameters (required to build a new index)",
)
@click.option(
    "--profile",
    "-pr",
    "selected_profile",
    type=str,
    required=False,
    help="⚙️  Profile name to use (default: uses default_profile from the profiles file)",
)
@click.option(
    "--fingerprint-file",
    "-ff",
    "fingerprint_file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    required=False,
    help="📋  Fingerprint YAML file produced by a previous compose run (required to update an existing index)",
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
    input_file,
    output_dir,
    profiles_file,
    fingerprint_file,
    selected_profile,
    session,
    name,
    partition_count,
    bf_max_size,
    partition_min_size,
    partition_count_limit,
):
    """Compose index definition file(s) from a sample list.

    Use --profiles-file to build a new index, or --fingerprint-file to update an existing one.
    Exactly one of the two must be provided.

    Examples:

      \b
      kmhelpers compose samples.jsonl -o ./db -f profiles.yaml

      \b
      kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --profile baseline

      \b
      kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --partition-count 4

      \b
      kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --partition-min-size 500MB

      \b
      kmhelpers compose samples.jsonl -o ./db -f profiles.yaml --split-size 10GB
    """

    try:
        if bool(profiles_file) == bool(fingerprint_file):
            raise click.UsageError(
                "Exactly one of --profiles-file or --fingerprint-file must be provided"
            )

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
            fingerprint_file=fingerprint_file,
            selected_profile=selected_profile,
            session=session,
            name=name,
            partition_count=partition_count,
            bf_max_size=bf_max_size,
            partition_min_size=partition_min_size,
            no_merge=False,
            exact_partition_count=False,
            partition_count_limit=partition_count_limit,
        ).run(input_file=input_file, output_dir=output_dir)

    except click.BadParameter:
        raise
    except Exception as e:
        raise click.ClickException(f"Compose failed: {e}")
