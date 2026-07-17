"""Query command for searching sequences in indices."""

import logging
import time

import click

from pykmhelpers import KmindexRegistry, QueryRunner, QueryRunnerConfig

logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--registry-path",
    "-r",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="📁  Path to kmindex registry.",
)
@click.option(
    "--index-ids",
    "-n",
    multiple=True,
    required=False,
    help="⚙   Index ID(s) to query against (can specify multiple, default: all).",
)
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory for query results.",
)
@click.option(
    "--zvalue",
    "-z",
    type=int,
    default=6,
    show_default=True,
    help="⚙   Z-value for findere algorithm, to filter false positives.",
)
@click.option(
    "--threshold",
    "-R",
    type=float,
    default=0.05,
    show_default=True,
    help="🎯  Score threshold for results filtering.",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    show_default=True,
    help="⚙️  Number of threads for parallel execution.",
)
@click.option(
    "--single-query",
    "-s",
    help="⚙   Treat all sequences as single query with this identifier.",
)
@click.option(
    "--batch-query",
    "-b",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Treat all sequences across all query files as a single batched query instead of querying each sequence individually.",
)
@click.option(
    "--aggregate",
    "-a",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Aggregate batch results into one file.",
)
@click.option(
    "--compressed",
    "-c",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Index is compressed.",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "yaml", "md", "html", "csv"]),
    default="json",
    show_default=True,
    help="⚙   Output format for results.",
)
@click.option(
    "--print",
    "-p",
    "print_output",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Print result to console (stdout).",
)
@click.option(
    "--timestamp",
    "-T",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Append a timestamp suffix to the output directory name to avoid overwriting previous results.",
)
@click.option(
    "--existing",
    "-e",
    type=click.Choice(["skip", "fail", "delete", "new-name"]),
    default="skip",
    show_default=True,
    help="⚙   Action when result directory already exists: skip, fail, delete, new-name.",
)
@click.option(
    "--parallel",
    "-P",
    type=click.Choice(["seq", "sub"]),
    default="seq",
    show_default=True,
    help="⚙   Parallelization strategy: seq (across sequences) or sub (across sub-indices). ‼️ Forced to sub when --compressed is set.",
)
@click.argument(
    "query_files",
    nargs=-1,
    required=True,
)
@click.pass_context
def query(
    ctx,
    registry_path,
    index_ids,
    output_dir,
    zvalue,
    threshold,
    threads,
    single_query,
    batch_query,
    aggregate,
    compressed,
    format,
    print_output,
    timestamp,
    existing,
    parallel,
    query_files,
):
    """Query indices with FASTA/FASTQ sequences.

    \b
    Input:  FASTA/FASTQ file(s), kmindex registry (-r)
    Output: result files in output directory (-o)

    QUERY_FILES: Query file(s) or directory/ies in FASTA/FASTQ format. Directories are
    scanned recursively. Use '-' to read from stdin.

    Examples:
      # Single query file against single index
      kmhelpers query -r ./registry -n idx1 -o results query.fa

      # Multiple query files with threading
      kmhelpers query -r ./registry -n idx1 -t 4 -o results q1.fa q2.fa

      # Multiple indices
      kmhelpers query -r ./registry -n idx1 -n idx2 -o results query.fa

      # Pipe from stdin
      cat query.fa | kmhelpers query -r ./registry -n idx1 -o results -

      # Treat all sequences as one query
      kmhelpers query -r ./registry -n idx1 --single-query batch1 -o out multi.fa

      # Scan a directory recursively
      kmhelpers query -r ./registry -n idx1 -o results ./queries_dir/
    """
    registry = KmindexRegistry(registry_path)

    if index_ids:
        for idx_id in index_ids:
            if idx_id not in registry:
                raise click.BadParameter(f"Index {idx_id} not found in registry")

    force = (ctx.obj or {}).get("yes", False)

    if existing == "delete" and not force:
        if not click.confirm(
            f"Proceed with 'delete' on existing output directories?", default=True
        ):
            raise click.Abort()
        force = True

    runner = QueryRunner(
        QueryRunnerConfig(
            registry_path=registry_path,
            output_dir=output_dir,
            index_ids=list(index_ids),
            zvalue=zvalue,
            threshold=threshold,
            threads=threads,
            single_query=single_query,
            batch=batch_query,
            aggregate=aggregate,
            compressed=compressed,
            output_format=format,
            print_output=print_output,
            timestamp=timestamp,
            on_existing=existing,
            parallel=parallel,
            force=force,
        )
    )

    start = time.time()
    try:
        runner.run(query_files)
    except (FileNotFoundError, FileExistsError, RuntimeError) as e:
        raise click.ClickException(str(e))

    logger.info(f"Completed in {time.time() - start:.2f}s")
    logger.info(f"Output directory: {output_dir}")
