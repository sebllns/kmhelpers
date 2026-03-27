"""Direct wrapper to kmindex built-in commands."""

import os

import click

from pykmhelpers import KmindexRegistry, KmindexWrapper
from pykmhelpers.cli.shared import estimate_build_size


@click.group()
def kmindex():
    """Wrapper commands for low-level interaction with kmindex."""
    pass


@kmindex.command("build")
@click.option(
    "--fof",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="File-of-Files (FOF) listing input samples",
)
@click.option(
    "--output-registry",
    "-r",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output kmindex registry path (created if doesn't exist)",
)
@click.option(
    "--output-index-dir",
    default=".subindexes",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Directory for index data (default: .subindexes)",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    help="K-mer size (default: 25)",
)
@click.option(
    "--minim-size",
    "-m",
    type=int,
    default=10,
    help="Minimizer size (default: 10)",
)
@click.option(
    "--bloom-size",
    type=int,
    help="Bloom filter size for presence/absence (mutually exclusive with --nb-cell)",
)
@click.option(
    "--nb-cell",
    type=int,
    help="Number of cells for abundance counting (mutually exclusive with --bloom-size)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="Number of threads (default: 1)",
)
@click.option(
    "--register-as",
    "-n",
    help="Register index with this ID (auto-generated if not provided)",
)
@click.option(
    "--compress-intermediate",
    is_flag=True,
    help="Compress intermediate files during build",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt before building",
)
def build(
    fof,
    output_registry,
    output_index_dir,
    kmer_size,
    minim_size,
    bloom_size,
    nb_cell,
    threads,
    register_as,
    compress_intermediate,
    verbose,
    force,
):
    """Build k-mer index from FOF file.

    Examples:
      # Build presence/absence index
      kmhelpers build --fof samples.fof -r ./registry --bloom-size 10000000

      # Build abundance index with custom k-mer size
      kmhelpers build --fof samples.fof -r ./registry --nb-cell 65536 -k 31

      # Build with multiple threads and register
      kmhelpers build --fof samples.fof -r ./registry --bloom-size 10000000 -t 8 -n my_index
    """

    # Validate parameters
    if bloom_size is None and nb_cell is None:
        raise click.BadParameter("Must specify either --bloom-size or --nb-cell")

    if bloom_size is not None and nb_cell is not None:
        raise click.BadParameter("Cannot specify both --bloom-size and --nb-cell")

    if minim_size >= kmer_size:
        raise click.BadParameter(
            f"minim-size ({minim_size}) must be less than kmer-size ({kmer_size})"
        )

    try:
        click.echo("Initializing build...")
        wrapper = KmindexWrapper()

        click.echo(f"Building index from FOF: {fof}")
        click.echo(f"  K-mer size: {kmer_size}")
        click.echo(f"  Minimizer size: {minim_size}")

        if bloom_size is not None:
            click.echo(f"  Bloom size: {bloom_size}")
        if nb_cell is not None:
            click.echo(f"  Abundance cells: {nb_cell}")

        click.echo(f"  Threads: {threads}")

        # Show confirmation with size estimation (skip if -f/--force is used)
        if not force:
            click.echo()
            try:
                size_est = estimate_build_size(
                    fof, bloom_size=bloom_size, nb_cell=nb_cell
                )
                click.echo("Build Size Estimate:")
                # click.echo(
                #     f"  Input data: {size_est['input_size_str']} ({size_est['sample_count']} samples)"
                # )
                click.echo(f"  Estimated index size: {size_est['index_size_min_str']}")
                click.echo()

                if not click.confirm("Proceed with build?", default=True):
                    click.echo("Build cancelled")
                    return
            except Exception as e:
                click.echo(f"Warning: Could not estimate build size: {e}", err=True)
                if not click.confirm("Proceed with build anyway?", default=True):
                    click.echo("Build cancelled")
                    return
            click.echo()

        # Build index using wrapper
        index_path, registry_path = wrapper.build(
            input_fof_file=fof,
            output_registry_path=output_registry,
            output_index_dir=output_index_dir,
            k=kmer_size,
            minim_size=minim_size,
            bloom_size=bloom_size,
            nb_cell=nb_cell,
            threads=threads,
            compress_intermediate=compress_intermediate,
            register_as=register_as,
        )

        click.echo(f"✓ Build completed successfully")
        click.echo(f"  Index directory: {index_path}")
        click.echo(f"  Registry: {registry_path}")

        # Show registered index info
        if register_as:
            registry = KmindexRegistry(output_registry)
            if registry.has_index(register_as):
                index = registry.get_index(register_as)
                click.echo(f"  Registered as: {register_as}")
                click.echo(f"    Samples: {index.nb_samples}")
                click.echo(f"    Partitions: {index.nb_partitions}")

    except Exception as e:
        raise click.ClickException(f"Build failed: {e}")


@kmindex.command("query")
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
    # "-q",
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
    "-r",
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
    "-s",
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
