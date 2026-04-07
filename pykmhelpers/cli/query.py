"""Query command for searching sequences in indices."""

import logging
import os
import shutil
import sys
import tempfile
import time

import click

from pykmhelpers import KmindexQuery, KmindexQueryResult, KmindexRegistry

logger = logging.getLogger(__name__)


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
    "-o",
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
    "-f",
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
    "--timestamp",
    "-T",
    is_flag=True,
    help="Append a timestamp suffix to the output directory name to avoid overwriting previous results",
)
@click.option(
    "--delete",
    "-d",
    is_flag=True,
    help="Delete the output directory before running if it already exists",
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
    aggregate,
    compressed,
    format,
    print,
    timestamp,
    delete,
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

    if timestamp:
        suffix = time.strftime("%Y%m%d_%H%M%S")
        output_dir = f"{output_dir}_{suffix}"

    if delete and os.path.exists(output_dir):
        yes = (ctx.obj or {}).get("yes", False)
        if not yes and not click.confirm(
            f"Delete existing output directory '{output_dir}'?"
        ):
            raise click.Abort()
        logger.debug(f"Deleting existing output directory: {output_dir}")
        shutil.rmtree(output_dir)

    logger.debug(f"Registry: {registry_path}")
    logger.debug(f"Indices: {', '.join(index_ids)}")
    logger.debug(f"Query files: {', '.join(resolved_files)}")

    os.makedirs(output_dir, exist_ok=True)

    total_queries = len(resolved_files)
    start_time = time.time()

    try:
        for query_idx, qfile in enumerate(resolved_files, 1):
            try:
                _run_query(
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
                    qfile,
                    total_queries,
                    query_idx,
                )
            except Exception as e:
                logger.error(f"Error querying {qfile}: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Completed in {elapsed:.2f}s")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Query files processed: {total_queries}")

    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")
    finally:
        for tmp in temp_files:
            os.unlink(tmp)


def _run_query(
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
    qfile,
    total_queries,
    query_idx,
):
    start_time = time.time()

    qfile_name = os.path.splitext(os.path.basename(qfile))[0]
    query_output = os.path.join(output_dir, qfile_name)

    logger.info(f"[{query_idx}/{total_queries}] Querying: {qfile_name}...")

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
        fast=not compressed,
        threshold=threshold,
    )

    elapsed = time.time() - start_time

    logger.debug(f"Time: {elapsed:.2f}s")

    result_dir = os.path.join(query_output, "result")

    if format != "json":
        for fname in os.listdir(result_dir):
            if fname.endswith(".json"):
                json_path = os.path.join(result_dir, fname)
                result = KmindexQueryResult(json_path)
                stem = os.path.splitext(fname)[0]
                out_file = os.path.join(result_dir, f"{stem}.{format}")
                formatted_result = result.convert(format=format, threshold=threshold)
                logger.debug(f"Converted: {out_file}")
                if print:
                    logger.info(formatted_result)
                else:
                    with open(out_file, "w") as f:
                        f.write(formatted_result)
    else:
        logger.debug(f"Results: {result_dir}")
