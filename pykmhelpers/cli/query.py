"""Query command for searching sequences in indices."""

import os
import sys
import tempfile

import click

from pykmhelpers import KmindexQuery, KmindexQueryResult, KmindexRegistry


@click.command()
@click.option(
    "--registry-path",
    "-r",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.option(
    "--index-ids",
    "-n",
    multiple=True,
    required=False,
    help="Index ID(s) to query against (can specify multiple, default: all)",
)
@click.option(
    "--output-dir",
    "-d",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for query results",
)
@click.option(
    "--zvalue",
    "-z",
    type=int,
    default=6,
    help="Z-value for findere algorithm, to filter false positives (default: 6)",
)
@click.option(
    "--threshold",
    "-e",
    type=float,
    default=0.05,
    help="Score threshold for results filtering (default: 0.05)",
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
    "-s",
    help="Treat all sequences as single query with this identifier",
)
@click.option(
    "--aggregate",
    "-a",
    is_flag=True,
    help="Aggregate batch results into one file",
)
@click.option(
    "--compressed",
    "-c",
    is_flag=True,
    help="Index is compressed",
)
@click.option(
    "--format",
    "-o",
    type=click.Choice(["json", "yaml", "md", "html", "csv"]),
    default="json",
    help="Output format for results (default: json)",
)
@click.option(
    "--print",
    "-p",
    is_flag=True,
    help="Print result to console (stderr)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
@click.argument(
    "query_files",
    nargs=-1,
    required=True,
)
def query(
    registry_path,
    index_ids,
    output_dir,
    zvalue,
    threshold,
    threads,
    single_query,
    aggregate,
    compressed,
    format,
    print,
    verbose,
    query_files,
):
    """Query indices with FASTA/FASTQ sequences.

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

    # Verify registry and indices
    registry = KmindexRegistry(registry_path)
    available_indices = registry.list_indices()

    if not index_ids:
        index_ids = tuple(available_indices)
    else:
        for idx_id in index_ids:
            if idx_id not in available_indices:
                raise click.BadParameter(f"Index {idx_id} not found in registry")

    # Resolve query files, handling '-' as stdin
    resolved_files = []
    temp_files = []
    for qfile in query_files:
        if qfile == "-":
            tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".fa", delete=False)
            tmp.write(sys.stdin.buffer.read())
            tmp.close()
            resolved_files.append(tmp.name)
            temp_files.append(tmp.name)
        else:
            if not os.path.exists(qfile):
                raise click.BadParameter(
                    f"File not found: {qfile}", param_hint="QUERY_FILES"
                )
            if os.path.isdir(qfile):
                for root, _, files in os.walk(qfile):
                    for fname in files:
                        resolved_files.append(os.path.join(root, fname))
            else:
                resolved_files.append(qfile)

    if verbose:
        click.echo(f"Registry: {registry_path}")
        click.echo(f"Indices: {', '.join(index_ids)}")
        click.echo(f"Query files: {', '.join(resolved_files)}\n")

    os.makedirs(output_dir, exist_ok=True)

    total_queries = len(resolved_files)

    try:
        for query_idx, qfile in enumerate(resolved_files, 1):
            qfile_name = os.path.splitext(os.path.basename(qfile))[0]
            query_output = os.path.join(output_dir, qfile_name)

            if verbose or total_queries > 1:
                click.echo(f"[{query_idx}/{total_queries}] Querying: {qfile_name}")

            kq = KmindexQuery(path=qfile)
            kq.execute(
                registry_path=registry_path,
                output_dir=query_output,
                index_ids=list(index_ids),
                z=zvalue,
                single_query=single_query,
                aggregate=aggregate,
                threads=threads,
                is_compressed=compressed,
            )

            if format != "json":
                result_dir = os.path.join(query_output, "result")
                for fname in os.listdir(result_dir):
                    if fname.endswith(".json"):
                        json_path = os.path.join(result_dir, fname)
                        result = KmindexQueryResult(json_path)
                        stem = os.path.splitext(fname)[0]
                        out_file = os.path.join(result_dir, f"{stem}.{format}")
                        formatted_result = result.convert(
                            format=format, threshold=threshold
                        )
                        if verbose:
                            click.echo(f"  Converted: {out_file}")
                        if print:
                            click.echo(formatted_result, err=True)
            elif verbose:
                click.echo(f"  Results: {os.path.join(query_output, 'result')}")

        click.echo(f"✓ Query completed")
        click.echo(f"  Output directory: {output_dir}")
        click.echo(f"  Query files processed: {total_queries}")

    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")
    finally:
        for tmp in temp_files:
            os.unlink(tmp)
