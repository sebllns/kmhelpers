#!/usr/bin/env python3
"""
Unified CLI for kmhelpers - a toolkit for managing, compressing, and querying k-mer indices.
"""

import os
import click

from kmhelpers import Main, KmindexRegistry, KmtricksIndex, Compressor, CompressionParams, KmindexWrapper


@click.group()
def cli():
    """kmhelpers - A toolkit for managing, compressing, and querying k-mer indices."""
    pass


# ============================================================================
# REGISTRY COMMANDS
# ============================================================================

@cli.group()
def registry():
    """Manage k-mer index registries."""
    pass


@registry.command(name="add")
@click.option(
    "--input-dir",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing kmtricks indices",
)
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Path to kmindex registry (created if doesn't exist)",
)
@click.option(
    "--index-ids",
    "-n",
    multiple=True,
    help="Specific index IDs to register (register all if not specified)",
)
def registry_add(input_dir, registry_path, index_ids):
    """Register kmtricks indices in a registry."""
    Main.init()
    click.echo("Initializing kmhelpers...")

    registry = KmindexRegistry(registry_path)

    # Get list of indices to register
    if index_ids:
        indices_to_process = index_ids
    else:
        indices_to_process = [d for d in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, d))]

    registered = 0
    skipped = 0

    for index_id in indices_to_process:
        entry_path = os.path.join(input_dir, index_id)
        if not os.path.isdir(entry_path):
            click.echo(f"Warning: {index_id} is not a directory, skipping", err=True)
            continue

        try:
            index = KmtricksIndex(input_dir, index_id)
            index.load_kmtricks_index()
            if index.check_structure():
                if registry.add_index(index):
                    click.echo(f"✓ Registered: {index_id}")
                    registered += 1
                else:
                    click.echo(f"⊙ Already registered: {index_id}")
                    skipped += 1
        except Exception as e:
            click.echo(f"✗ Error processing {index_id}: {e}", err=True)

    click.echo(f"\nSummary: {registered} registered, {skipped} skipped")


@registry.command(name="list")
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
def registry_list(registry_path):
    """List all indices in a registry."""
    Main.init()
    registry = KmindexRegistry(registry_path)

    indices = registry.list_indices()
    if not indices:
        click.echo("No indices found in registry")
        return

    click.echo(f"Registry: {registry_path}")
    click.echo(f"Available indices ({len(indices)} total):")
    for idx_name in indices:
        idx = registry.get_index(idx_name)
        click.echo(f"  • {idx_name} ({idx.nb_samples} samples, {idx.nb_partitions} partitions, k={idx.kmer_size})")


# ============================================================================
# COMPRESSION COMMANDS
# ============================================================================

@cli.command()
@click.option(
    "--input-dir",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing kmtricks indices",
)
@click.option(
    "--index-id",
    "-n",
    required=True,
    help="Index ID to compress",
)
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for compressed index",
)
@click.option(
    "--ref-matrix",
    type=int,
    default=1,
    help="Reference partition for permutation computation (default: 1)",
)
@click.option(
    "--matrices",
    "-m",
    multiple=True,
    type=int,
    help="Specific partitions to compress (compress all if not specified)",
)
@click.option(
    "--block-size",
    type=int,
    default=8388608,
    help="Block size for compression in bytes (default: 8MB)",
)
@click.option(
    "--subsample-size",
    type=int,
    default=20000,
    help="Rows to sample for computing distances (default: 20000)",
)
@click.option(
    "--enable-metrics",
    is_flag=True,
    default=True,
    help="Enable compression metrics collection",
)
def compress(input_dir, index_id, output_dir, ref_matrix, matrices, block_size, subsample_size, enable_metrics):
    """Compress k-mer index partitions."""
    Main.init()
    click.echo("Initializing compression...")

    # Load index
    index = KmtricksIndex(input_dir, index_id)
    index.load_kmtricks_index()
    click.echo(f"Loaded index: {index}")

    # Determine which matrices to compress
    if matrices:
        matrix_list = list(matrices)
    else:
        matrix_list = [i for i in range(index.nb_partitions) if i != ref_matrix]

    # Create compression parameters
    params = CompressionParams(
        block_size=block_size,
        subsample_size=subsample_size,
        enable_overwrite=True,
    )

    # Create compressor
    compressor = Compressor(enable_metrics=enable_metrics)

    click.echo(f"Compressing {len(matrix_list)} partitions (reference: {ref_matrix})...")
    click.echo(f"Block size: {block_size}, Subsample size: {subsample_size}")

    try:
        compressor.compress_index_selection(
            params,
            index,
            ref_matrix,
            matrix_list,
            output_dir,
        )
        click.echo(f"✓ Compression completed successfully")
        click.echo(f"Output directory: {output_dir}")
    except Exception as e:
        raise click.ClickException(f"Compression failed: {e}")


# ============================================================================
# QUERY COMMANDS
# ============================================================================

@cli.command()
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
    help="Index ID(s) to query against",
)
@click.option(
    "--query-file",
    "-q",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Query file in FASTA/FASTQ format",
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
    default=0,
    help="Z-value for kmindex (default: 0)",
)
@click.option(
    "--threshold",
    type=float,
    default=0.0,
    help="Score threshold for results filtering (default: 0.0)",
)
def query(registry_path, index_ids, query_file, output_dir, zvalue, threshold):
    """Query indices with FASTA/FASTQ sequences."""
    Main.init()
    click.echo(f"Querying with: {query_file}")

    # Verify registry and indices
    registry = KmindexRegistry(registry_path)
    available_indices = registry.list_indices()

    for idx_id in index_ids:
        if idx_id not in available_indices:
            raise click.BadParameter(f"Index {idx_id} not found in registry")

    os.makedirs(output_dir, exist_ok=True)

    # Create wrapper and perform query
    wrapper = KmindexWrapper()

    try:
        results_dir = wrapper.query(
            input_registry=registry_path,
            query_file=query_file,
            output_dir=output_dir,
            names=list(index_ids),
            zvalue=zvalue,
            threshold=threshold,
        )
        click.echo(f"✓ Query completed")
        click.echo(f"Results directory: {results_dir}")
    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")


if __name__ == "__main__":
    cli()
