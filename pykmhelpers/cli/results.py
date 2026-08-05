"""Inspect, check, or convert existing kmindex query results."""

import logging

import click

from pykmhelpers.pipeline.query import KMINDEX_QUERY_OUTPUT, KmindexQueryResult

logger = logging.getLogger(__name__)


@click.command(name="results")
@click.argument(
    "results_dirs",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--check",
    "-C",
    "check_sample",
    metavar="SAMPLE",
    help="Assert SAMPLE's max score across all merged results meets --min-score; "
    "exit non-zero on failure instead of printing/converting results. For CI gates.",
)
@click.option(
    "--min-score",
    "-m",
    type=float,
    default=0.9,
    show_default=True,
    help="Minimum score required for --check to pass.",
)
@click.option(
    "--format",
    "-f",
    "format_",
    type=click.Choice(["tsv", "json", "md", "html", "yaml"]),
    default="tsv",
    show_default=True,
    help="Output format for converted results (ignored with --check).",
)
@click.option(
    "--threshold",
    "-R",
    type=float,
    default=0.01,
    show_default=True,
    help="Minimum score for a result row to be included in converted output (ignored with --check).",
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(dir_okay=False),
    required=False,
    help="Write converted results to this file instead of printing to console (ignored with --check).",
)
@click.option(
    "--subdir",
    default=KMINDEX_QUERY_OUTPUT,
    show_default=True,
    help="Name of the kmindex output subdirectory to scan for *.jsonl files under each RESULTS_DIRS.",
)
def results(
    results_dirs,
    check_sample,
    min_score,
    format_,
    threshold,
    output_file,
    subdir,
):
    """Inspect, check, or convert existing kmindex query results.

    \b
    Input:  one or more result directories previously produced by `kmhelpers query`
    Output: an OK/FAIL check result (--check), or a converted report (stdout or --output)

    RESULTS_DIRS: one or more directories to scan recursively for
    `**/kmindex_output/*.jsonl` files (the layout `kmhelpers query` writes).
    Matching files are merged into a single result set before checking or converting.

    Examples:
      # CI gate: fail (exit 1) unless SAMPLE scored >= 0.9 anywhere in results/
      kmhelpers results results/ --check my_sample

      # CI gate with a custom threshold
      kmhelpers results results/ --check my_sample --min-score 0.95

      # Print a readable score matrix to the console (default format: tsv)
      kmhelpers results results/

      # Convert merged results to markdown and print to console
      kmhelpers results results/ -f md

      # Convert merged results to JSON and write to a file
      kmhelpers results results/ -f json -o merged.json

      # Merge several result directories from separate query runs
      kmhelpers results results_run1/ results_run2/ --check my_sample
    """
    label = ", ".join(results_dirs)
    jsonl_files = list(
        KmindexQueryResult.iter_result_files(results_dirs, subdir=subdir)
    )

    if not jsonl_files:
        message = f"no {subdir}/*.jsonl under {label}"
        if check_sample:
            click.echo(f"FAIL: {message}", err=True)
            raise SystemExit(1)
        raise click.ClickException(message)

    merged = KmindexQueryResult()
    for jf in jsonl_files:
        try:
            merged.load_jsonl(str(jf))
        except Exception as e:
            logger.warning(f"Failed to read {jf}: {e}")

    if check_sample:
        score = merged.max_score(check_sample)
        if score < min_score:
            click.echo(
                f"FAIL: {check_sample} scored {score} (< {min_score}) in {label}",
                err=True,
            )
            raise SystemExit(1)
        click.echo(f"OK: {check_sample} scored {score:.3f} in {label}")
        return

    try:
        converted = merged.convert(format=format_, threshold=threshold)
    except ValueError as e:
        raise click.ClickException(str(e))

    if output_file:
        with open(output_file, "w") as f:
            f.write(converted)
        logger.info(f"Results: {output_file}")
    else:
        click.echo(converted)
