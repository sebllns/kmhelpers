"""Compression commands for k-mer indices.

This module provides two approaches to index compression:
1. compress: Direct partition compression with advanced options (sampling, permutation, etc.)
2. kmindex-compress: Registry-based compression using the KmindexWrapper
"""

import os
import click
from .experimental import experimental
from pykmhelpers import KmindexRegistry, KmtricksIndex, Compressor, CompressionParams
from pykmhelpers.operations.compressor import PermutationFlag


@experimental.command(name="compress")
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
    "--group-size",
    type=int,
    default=0,
    help="Columns to group during permutation (default: 0 = all)",
)
@click.option(
    "--threshold",
    type=float,
    default=0.0,
    help="Threshold for permutation algorithm (default: 0.0)",
)
@click.option(
    "--enable-check",
    is_flag=True,
    help="Verify decompression against original",
)
@click.option(
    "--with-size-comparison",
    is_flag=True,
    default=True,
    help="Generate size comparison CSV",
)
@click.option(
    "--compare-unordered",
    is_flag=True,
    help="Also compress without ordering for benchmarking",
)
@click.option(
    "--enable-metrics",
    "--metrics",
    is_flag=True,
    default=True,
    help="Enable compression metrics collection",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing output directory",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def compress(
    input_dir,
    index_id,
    output_dir,
    ref_matrix,
    matrices,
    block_size,
    subsample_size,
    group_size,
    threshold,
    enable_check,
    with_size_comparison,
    compare_unordered,
    enable_metrics,
    force,
    verbose,
):
    """Compress k-mer index partitions.

    Direct partition compression with advanced options. Uses permutation-based
    reordering and per-partition compression for fine-grained control.

    Examples:
      # Compress all partitions with default settings
      kmhelpers compress -i ./indices -n my_index -o ./compressed

      # Compress specific partitions with size comparison
      kmhelpers compress -i ./indices -n my_index -o ./out -m 1 -m 2 -m 3 --compare-unordered

      # Custom block size with verification
      kmhelpers compress -i ./indices -n my_index -o ./out --block-size 16777216 --enable-check
    """

    # Check if output dir exists
    if os.path.exists(output_dir) and not force:
        raise click.ClickException(
            f"Output directory exists. Use --force to overwrite."
        )

    click.echo("Initializing compression...")

    try:
        # Load index
        index = KmtricksIndex(input_dir, index_id)
        index.load_kmtricks_index()

        if verbose:
            click.echo(f"Loaded index: {index}")

        # Validate ref_matrix
        if ref_matrix >= index.nb_partitions:
            raise click.BadParameter(
                f"ref-matrix {ref_matrix} exceeds partition count {index.nb_partitions}"
            )

        # Determine which matrices to compress
        if matrices:
            matrix_list = list(matrices)
        else:
            matrix_list = [i for i in range(index.nb_partitions) if i != ref_matrix]

        # Create compression parameters with all options
        params = CompressionParams(
            block_size=block_size,
            group_size=group_size,
            subsample_size=subsample_size,
            threshold=threshold,
            enable_check=enable_check,
            enable_overwrite=True,
            with_size_comparison=with_size_comparison,
        )

        # Create compressor
        compressor = Compressor(enable_metrics=enable_metrics)

        click.echo(
            f"Compressing {len(matrix_list)} partitions (reference: {ref_matrix})..."
        )
        click.echo(f"  Block size: {block_size} bytes")
        click.echo(f"  Subsample size: {subsample_size}")
        click.echo(f"  Group size: {group_size}")
        click.echo(f"  Threshold: {threshold}")

        if enable_check:
            click.echo(f"  With verification: yes")
        if compare_unordered:
            click.echo(f"  With unordered comparison: yes")

        compressor.compress_index_selection(
            params,
            index,
            ref_matrix,
            matrix_list,
            output_dir,
            permutation_flag=PermutationFlag.PERMUTATION_ENABLED,
            compare_unordered=compare_unordered,
        )

        click.echo(f"✓ Compression completed successfully")
        click.echo(f"  Output directory: {output_dir}")

        if enable_metrics:
            click.echo(f"  Metrics saved in: {os.path.join(output_dir, 'metrics')}")
        if with_size_comparison:
            click.echo(
                f"  Size comparison in: {os.path.join(output_dir, 'metrics', 'sizes.csv')}"
            )

    except Exception as e:
        raise click.ClickException(f"Compression failed: {e}")
