"""Query command for searching sequences in indices."""

import logging
import os
import shutil
import sys
import tempfile
import time

import click

from pykmhelpers import KmindexQuery, KmindexQueryResult, KmindexRegistry
from pykmhelpers.core.constants import DATA_EXT

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
    "-T",
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
    "--batch-query",
    "-b",
    is_flag=True,
    help="Treat all sequences across all query files as a single batched query instead of querying each sequence individually",
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
    "-P",
    is_flag=True,
    help="Append a timestamp suffix to the output directory name to avoid overwriting previous results",
)
@click.option(
    "--existing",
    "-e",
    type=click.Choice(["skip", "fail", "delete", "new-name"]),
    default="skip",
    help="Action when result directory already exists: skip (default), fail, delete, new-name",
)
@click.option(
    "--method",
    "-M",
    type=click.Choice(["seq", "sub"]),
    default="seq",
    help="Query method: seq (parallelizes across sequences, default) or sub (parallelizes across sub-indices). Forced to sub when --compressed is set.",
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
    print,
    timestamp,
    existing,
    method,
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

    if compressed and method != "sub":
        logger.warning("--compressed requires sub method, ignoring --method")
        method = "sub"

    # Verify registry and indices
    registry = KmindexRegistry(registry_path)

    if index_ids:
        for idx_id in index_ids:
            if idx_id not in registry:
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
                        if any(fname.endswith(ext) for ext in DATA_EXT):
                            resolved_files.append(os.path.join(root, fname))
            else:
                resolved_files.append(qfile)

    logger.debug(f"Query files: {', '.join(resolved_files)}")
    logger.debug(f"Registry: {registry_path}")
    logger.debug(
        f"Indices: {', '.join(index_ids if index_ids else registry.list_indices())}"
    )

    os.makedirs(output_dir, exist_ok=True)

    start_time = time.time()

    try:
        if batch_query:
            batch_path = os.path.join(tempfile.gettempdir(), "batch.fa")
            temp_files.append(batch_path)
            with open(batch_path, "wb") as batch_tmp:
                for qfile in resolved_files:
                    with open(qfile, "rb") as f:
                        batch_tmp.write(f.read())
            logger.info(f"Batching {len(resolved_files)} file(s) into a single query...")
            _run_query(
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
                existing,
                batch_path,
                1,
                1,
                method,
            )
        else:
            total_queries = len(resolved_files)
            for query_idx, qfile in enumerate(resolved_files, 1):
                try:
                    _run_query(
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
                        existing,
                        qfile,
                        total_queries,
                        query_idx,
                        method,
                    )
                except Exception as e:
                    logger.error(f"Error querying {qfile}: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Completed in {elapsed:.2f}s")
        logger.info(f"Output directory: {output_dir}")

    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")
    finally:
        for tmp in temp_files:
            os.unlink(tmp)


def _run_query(
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
    existing,
    qfile,
    total_queries,
    query_idx,
    method,
):
    start_time = time.time()

    qfile_name = os.path.splitext(os.path.basename(qfile))[0]
    query_output = os.path.join(output_dir, qfile_name)

    if timestamp:
        suffix = time.strftime("%Y%m%d_%H%M%S")
        query_output = f"{query_output}_{suffix}"

    if os.path.exists(query_output):
        if existing == "skip":
            logger.info(
                f"[{query_idx}/{total_queries}] Skipping {qfile_name}: output directory already exists"
            )
            return
        elif existing == "fail":
            raise click.ClickException(
                f"Output directory already exists: {query_output}"
            )
        elif existing == "delete":
            yes = (ctx.obj or {}).get("yes", False)
            if not yes and not click.confirm(
                f"Delete existing output directory '{query_output}'?"
            ):
                raise click.Abort()
            logger.debug(f"Deleting existing output directory: {query_output}")
            shutil.rmtree(query_output)
        elif existing == "new-name":
            suffix = time.strftime("%Y%m%d_%H%M%S")
            query_output = f"{query_output}_{suffix}"
            logger.debug(f"Output directory renamed to: {query_output}")

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
        method=method,
    )

    elapsed = time.time() - start_time
    result_dir = os.path.join(query_output, "result")

    # logger prints in stderr
    logger.info(
        f"Time: {elapsed:.2f}s",
    )
    logger.info(f"Results: {result_dir}")

    if format != "json":
        for fname in os.listdir(result_dir):
            if fname.endswith(".json"):
                try:
                    json_path = os.path.join(result_dir, fname)
                    result = KmindexQueryResult(json_path)
                    stem = os.path.splitext(fname)[0]
                    out_file = os.path.join(result_dir, f"{stem}.{format}")
                    formatted_result = result.convert(
                        format=format, threshold=threshold
                    )
                    logger.debug(f"Converted: {out_file}")
                    if print:
                        # click.echo prints in stdout
                        click.echo(formatted_result)
                    else:
                        with open(out_file, "w") as f:
                            f.write(formatted_result)
                except Exception as e:
                    logger.warning(f"Failed to convert {fname}: {e}")
