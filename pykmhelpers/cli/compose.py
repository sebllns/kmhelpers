"""Compose command: build index definition file(s) from lists of samples."""

import click

from pykmhelpers.cli.shared import force_verbose_mode
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.composer import compose_indices, parse_span_list


@click.command(name="compose")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
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
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    help="🧬  K-mer size (default: 25)",
)
@click.option(
    "--unassembled",
    is_flag=True,
    help="🧬  Treat input data as raw reads instead of assembled genomes",
)
@click.option(
    "--false-positive-rate",
    "--fp",
    type=float,
    default=0.25,
    help="🎯  Bloom filter false-positive rate (default: 0.25). "
    "A higher rate reduces disk footprint; the findere algorithm compensates at "
    "query time by using (k+z)-mers. Recommended: build with p=0.25, query with z=6.",
)
@click.option(
    "--recount",
    is_flag=True,
    default=False,
    help="🔄  Force recount k-mers for all samples (ignore cached kmer_count)",
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
    "--bf-max-size",
    "-b",
    help="💾  Maximum Bloom Filter size (e.g., '10GB', '5000MB') before splitting samples across indices (default = no limit)",
)
@click.option(
    "--partition-min-size",
    "-m",
    help="💾  Minimum partition file size (e.g., '500MB', '1GB'). If not met, partition count will decrease to maintain this size limit per partition (default = no limit)",
)
@click.option(
    "--no-merge",
    is_flag=True,
    default=False,
    help="⚙️   Treat each part of split indices as independent indices (mostly used for partition count calculation)",
)
@click.option(
    "--exact-partition-count",
    is_flag=True,
    default=False,
    help="⚙️   Keep exact partition count (default rounds to nearest power of 2)",
)
@click.option(
    "--partition-count-limit",
    type=int,
    default=256,
    help="⚙️   Partition count limit for auto-partitioning (default: 256)",
)
@click.option(
    "--ntcard-threads",
    "--ntt",
    type=int,
    default=8,
    help="⚙️  Number of threads used by ntcard for k-mer counting (default: 8)",
)
@click.option(
    "--ntcard-value",
    "--ntv",
    default="F0",
    help="⚙️   Value ID to extract from ntcard output (default: 'F0')",
)
@click.option(
    "--no-split",
    is_flag=True,
    default=False,
    help="⚙️   Export all index definitions to a single file",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    default="yaml",
    help="⚙️  Output format of created database (default: 'yaml')",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="🔊  Increase log level to INFO (unless already higher)",
)
def compose(
    input_files,
    output_dir,
    prefix,
    name,
    kmer_size,
    unassembled,
    span_list,
    partition_count,
    bf_max_size,
    partition_min_size,
    no_merge,
    exact_partition_count,
    partition_count_limit,
    ntcard_threads,
    ntcard_value,
    false_positive_rate,
    no_split,
    recount,
    format,
    verbose,
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
    if verbose:
        force_verbose_mode()

    try:
        if kmer_size <= 0:
            raise click.BadParameter(
                f"Constraint must be respected: k > 0 (got k = {kmer_size})"
            )
        if kmer_size >= 64:
            raise click.BadParameter(
                f"Constraint must be respected: k < 64 (got k = {kmer_size})"
            )
        if false_positive_rate <= 0:
            raise click.BadParameter(
                f"Constraint must be respected: false_positive_rate > 0 (got false_positive_rate = {false_positive_rate})"
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
            kmer_size=kmer_size,
            assembled=not unassembled,
            allowed_spans=allowed_spans,
            partition_count=partition_count,
            bf_max_size=bf_max_size,
            partition_min_size=partition_min_size,
            no_merge=no_merge,
            exact_partition_count=exact_partition_count,
            partition_count_limit=partition_count_limit,
            ntcard_threads=ntcard_threads,
            ntcard_value=ntcard_value,
            false_positive_rate=false_positive_rate,
            no_split=no_split,
            recount=recount,
            format=format,
        )

    except click.BadParameter:
        raise
    except Exception as e:
        raise click.ClickException(f"Compose failed: {e}")