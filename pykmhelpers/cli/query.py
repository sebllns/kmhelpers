"""Query command for searching sequences in indices."""

import os
import click
from pykmhelpers import KmindexRegistry, KmindexWrapper


@click.command()
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.option(
    "--index-ids",
    "-n",
    multiple=True,
    required=True,
    help="Index ID(s) to query against (can specify multiple)",
)
@click.option(
    "--query-file",
    "-q",
    multiple=True,
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Query file(s) in FASTA/FASTQ format (can specify multiple)",
)
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for query results",
)
@click.option(
    "--zvalue",
    type=int,
    default=6,
    help="Z-value for findere algorithm, to filter false positives (default: 6)",
)
@click.option(
    "--threshold",
    type=float,
    default=0.0,
    help="Score threshold for results filtering (default: 0.0)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="Number of threads for parallel execution (default: 1)",
)
@click.option(
    "--single-query",
    help="Treat all sequences as single query with this identifier",
)
@click.option(
    "--aggregate",
    is_flag=True,
    help="Aggregate batch results into one file",
)
@click.option(
    "--format",
    type=click.Choice(["json", "txt"]),
    default="json",
    help="Output format (default: json)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def query(
    registry_path,
    index_ids,
    query_file,
    output_dir,
    zvalue,
    threshold,
    threads,
    single_query,
    aggregate,
    format,
    verbose,
):
    """Query indices with FASTA/FASTQ sequences.

    Examples:
      # Single query file against single index
      kmhelpers query -r ./registry -n idx1 -q query.fa -o results

      # Multiple query files with threading
      kmhelpers query -r ./registry -n idx1 -q q1.fa -q q2.fa -t 4 -o results

      # Multiple indices
      kmhelpers query -r ./registry -n idx1 -n idx2 -q query.fa -o results

      # Treat all sequences as one query
      kmhelpers query -r ./registry -n idx1 -q multi.fa --single-query batch1 -o out
    """

    # Verify registry and indices
    registry = KmindexRegistry(registry_path)
    available_indices = registry.list_indices()

    for idx_id in index_ids:
        if idx_id not in available_indices:
            raise click.BadParameter(f"Index {idx_id} not found in registry")

    if verbose:
        click.echo(f"Registry: {registry_path}")
        click.echo(f"Indices: {', '.join(index_ids)}")
        click.echo(f"Query files: {', '.join(query_file)}\n")

    os.makedirs(output_dir, exist_ok=True)

    # Create wrapper and perform query
    wrapper = KmindexWrapper()
    total_queries = len(query_file)

    try:
        for query_idx, qfile in enumerate(query_file, 1):
            qfile_name = os.path.splitext(os.path.basename(qfile))[0]
            query_output = os.path.join(output_dir, qfile_name)

            if verbose or total_queries > 1:
                click.echo(f"[{query_idx}/{total_queries}] Querying: {qfile_name}")

            results_dir = wrapper.query(
                input_registry=registry_path,
                query_file=qfile,
                output_dir=query_output,
                names=list(index_ids),
                zvalue=zvalue,
                threshold=threshold,
                threads=threads,
                single_query=single_query,
                aggregate=aggregate,
                format=format,
            )

            if verbose:
                click.echo(f"  Results: {results_dir}")

        click.echo(f"✓ Query completed")
        click.echo(f"  Output directory: {output_dir}")
        click.echo(f"  Query files processed: {total_queries}")

    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")
