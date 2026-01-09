#!/usr/bin/env python3
"""
Unified CLI for kmhelpers - a toolkit for managing, compressing, and querying k-mer indices.
"""

import os
import click
import json
import yaml
from pathlib import Path

from pykmhelpers import (
    __version__,
    Main,
    KmindexRegistry,
    KmtricksIndex,
    Compressor,
    CompressionParams,
    KmindexWrapper,
)
from pykmhelpers.operations.fof import FofManager
from pykmhelpers.operations.fof_validation import FofValidator
from pykmhelpers.operations.compressor import PermutationFlag
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.operations.query import KmindexQuery, KmindexQueryResult


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="kmhelpers")
def cli():
    """kmhelpers - A toolkit for managing, compressing, and querying k-mer indices."""
    pass


# ============================================================================
# FOF (FILE-OF-FILES) COMMANDS
# ============================================================================


@cli.group()
def fof():
    """Manage File-of-Files (FOF) for index building."""
    pass


@fof.command(name="create")
@click.option(
    "--from-directory",
    "-d",
    "from_directory",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Directory containing FASTA/FASTQ files",
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False),
    help="Output FOF file path",
)
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help="Search subdirectories recursively",
)
@click.option(
    "--extensions",
    "-e",
    multiple=True,
    default=[".fasta", ".fastq", ".fa", ".fq", ".fasta.gz", ".fastq.gz"],
    help="File extensions to include (default: common bioinformatics formats)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
def fof_create(from_directory, output, recursive, extensions, verbose):
    """Create FOF file from directory of sequence files."""
    try:
        manager = FofManager()
        files = manager.list_files_in_directory(
            from_directory, recursive=recursive, extensions=list(extensions)
        )

        if not files:
            raise click.ClickException(
                f"No files found matching extensions {extensions}"
            )

        # Extract sample names and add to manager
        for file_path in files:
            sample_name = FofManager.extract_sample_name(file_path)
            manager.add_sample(file_path, sample_name)
            if verbose:
                click.echo(f"  Added: {sample_name} -> {file_path}")

        # Save to output file
        manager.save(output)

        click.echo(f"✓ Created FOF file: {output}")
        click.echo(f"  Samples: {manager.get_sample_count()}")

    except Exception as e:
        raise click.ClickException(f"Failed to create FOF: {e}")


@fof.command(name="validate")
@click.argument(
    "fof_file", type=click.Path(exists=True, file_okay=True, dir_okay=False)
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed validation output",
)
def fof_validate(fof_file, verbose):
    """Validate FOF file format and check sample files exist."""
    try:
        # Validate format
        validator = FofValidator(fof_file)
        is_valid = validator.validate()

        if is_valid:
            click.echo(f"✓ FOF format is valid: {fof_file}")
        else:
            click.echo(f"✗ FOF format errors in {fof_file}:", err=True)
            validator.print_errors()
            raise click.ClickException(
                f"FOF file has {validator.get_error_count()} validation error(s)"
            )

        # Check if sample files exist
        manager = FofManager(fof_file)
        missing_files = []

        for sample_id in manager.get_all_sample_ids():
            file_path = manager.get_sample_path(sample_id)
            if file_path is None or not os.path.isfile(file_path):
                missing_files.append((sample_id, file_path or "N/A"))
                if verbose:
                    click.echo(f"  Missing: {sample_id} -> {file_path}", err=True)

        if missing_files:
            raise click.ClickException(
                f"Found {len(missing_files)} missing sample file(s)"
            )

        click.echo(f"  Files: {manager.get_sample_count()} samples exist")

    except FileNotFoundError as e:
        raise click.ClickException(f"FOF file not found: {e}")
    except Exception as e:
        raise click.ClickException(f"Validation failed: {e}")


@fof.command(name="list")
@click.argument(
    "fof_file", type=click.Path(exists=True, file_okay=True, dir_okay=False)
)
@click.option(
    "--show-paths",
    is_flag=True,
    help="Show full file paths",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
def fof_list(fof_file, show_paths, output_json):
    """List all samples in FOF file."""
    try:
        manager = FofManager(fof_file)
        sample_ids = manager.get_all_sample_ids()

        if not sample_ids:
            click.echo("No samples found in FOF file")
            return

        if output_json:
            # Output as JSON
            data = {
                "fof_file": fof_file,
                "sample_count": len(sample_ids),
                "samples": [
                    {"id": sid, "path": manager.get_sample_path(sid)}
                    for sid in sample_ids
                ],
            }
            click.echo(json.dumps(data, indent=2))
        else:
            # Output as table
            click.echo(f"FOF File: {fof_file}")
            click.echo(f"Samples: {len(sample_ids)}\n")

            for sample_id in sample_ids:
                file_path = manager.get_sample_path(sample_id)
                if show_paths:
                    click.echo(f"  {sample_id:<30} {file_path}")
                else:
                    click.echo(f"  {sample_id}")

    except Exception as e:
        raise click.ClickException(f"Failed to list FOF samples: {e}")


@fof.command(name="add")
@click.option(
    "--fof",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="FOF file to modify",
)
@click.option(
    "--sample-file",
    "-s",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Sample file to add",
)
@click.option(
    "--sample-id",
    "-n",
    help="Sample ID (auto-extracted from filename if not provided)",
)
def fof_add(fof, sample_file, sample_id):
    """Add sample to existing FOF file."""
    try:
        manager = FofManager(fof)

        # Auto-extract sample name if not provided
        if not sample_id:
            sample_id = FofManager.extract_sample_name(sample_file)

        # Check if sample already exists
        if manager.has_sample(sample_id):
            raise click.ClickException(f"Sample '{sample_id}' already exists in FOF")

        # Add sample and save
        manager.add_sample(sample_file, sample_id)
        manager.save(fof)

        click.echo(f"✓ Added sample: {sample_id}")
        click.echo(f"  File: {sample_file}")
        click.echo(f"  Total samples: {manager.get_sample_count()}")

    except Exception as e:
        raise click.ClickException(f"Failed to add sample: {e}")


# ============================================================================
# BUILD COMMAND HELPERS
# ============================================================================


def estimate_build_size(
    fof_path: str, bloom_size: int = None, nb_cell: int = None
) -> dict:
    """
    Estimate the size required for building an index.

    Args:
        fof_path: Path to the FOF file
        bloom_size: Bloom filter size (for presence/absence)
        nb_cell: Number of cells (for abundance counting)

    Returns:
        Dictionary with size estimates (input_size, index_size_min, index_size_max)
    """
    # Load FOF and calculate input data size
    manager = FofManager()
    samples = manager.load_with_paths(fof_path)

    total_input_size = 0
    sample_count = len(samples)

    for sample_name, file_path in samples.items():
        if os.path.isfile(file_path):
            total_input_size += os.path.getsize(file_path)

    # Estimate index size based on index type
    # Bloom filter: bloom_size (in bytes) + overhead
    # Abundance: roughly (nb_cell * 4 bytes) + overhead

    if bloom_size is not None:
        # Bloom filter is specified in bits, convert to bytes
        index_size_estimate = bloom_size
    elif nb_cell is not None:
        # Abundance: each cell is typically 4 bytes (configurable with bitw)
        # Plus partitions overhead (roughly 100MB per partition estimated)
        index_size_estimate = nb_cell * 4
    else:
        index_size_estimate = 0


    min_estimate = index_size_estimate

    return {
        "input_size": total_input_size,
        "input_size_gb": total_input_size / (1024**3),
        "sample_count": sample_count,
        "index_size_min_gb": min_estimate / (1024**3),
    }


def format_size(bytes_size: float) -> str:
    """Format bytes to human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} PB"


# ============================================================================
# BUILD COMMAND
# ============================================================================


@cli.command()
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
    Main.init()

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
                click.echo(
                    f"  Input data: {size_est['input_size_gb']:.2f} GB ({size_est['sample_count']} samples)"
                )
                click.echo(
                    f"  Estimated index size: {size_est['index_size_min_gb']:.2f} - {size_est['index_size_max_gb']:.2f} GB"
                )
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
            verbose="debug" if verbose else "info",
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
        indices_to_process = [
            d
            for d in os.listdir(input_dir)
            if os.path.isdir(os.path.join(input_dir, d))
        ]

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
        click.echo(
            f"  • {idx_name} ({idx.nb_samples} samples, {idx.nb_partitions} partitions, k={idx.kmer_size})"
        )


@registry.command(name="info")
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.option(
    "--index-id",
    "-n",
    required=True,
    help="Index ID to show information for",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
def registry_info(registry_path, index_id, output_json):
    """Show detailed information about an index."""
    Main.init()

    try:
        registry = KmindexRegistry(registry_path)

        if not registry.has_index(index_id):
            raise click.ClickException(f"Index '{index_id}' not found in registry")

        index = registry.get_index(index_id)

        if output_json:
            # Output as JSON
            data = {
                "index_id": index.index_id,
                "nb_samples": index.nb_samples,
                "nb_partitions": index.nb_partitions,
                "kmer_size": index.kmer_size,
                "minim_size": index.minim_size,
                "bloom_size": index.bloom_size,
                "bytes_per_row": index.bytes_per_row,
                "index_size": index.index_size,
                "kmindex_version": index.kmindex_version,
                "kmtricks_version": index.kmtricks_version,
            }
            click.echo(json.dumps(data, indent=2))
        else:
            # Output as formatted text
            click.echo(f"Index Information: {index_id}")
            click.echo(f"  Samples: {index.nb_samples}")
            click.echo(f"  Partitions: {index.nb_partitions}")
            click.echo(f"  K-mer size: {index.kmer_size}")
            click.echo(f"  Minimizer size: {index.minim_size}")
            click.echo(f"  Bloom filter size: {index.bloom_size}")
            click.echo(f"  Bytes per row: {index.bytes_per_row}")
            click.echo(f"  Index size: {index.index_size} bytes")
            click.echo(f"  kmindex version: {index.kmindex_version}")
            click.echo(f"  kmtricks version: {index.kmtricks_version}")

    except Exception as e:
        raise click.ClickException(f"Failed to retrieve index info: {e}")


@registry.command(name="check")
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed validation output",
)
def registry_check(registry_path, verbose):
    """Validate registry consistency and check all index structures."""
    Main.init()

    try:
        registry = KmindexRegistry(registry_path)
        indices = registry.list_indices()

        if not indices:
            click.echo("No indices found in registry")
            return

        click.echo(f"Validating {len(indices)} index(ices)...\n")

        errors = []
        for idx_name in indices:
            try:
                index = registry.get_index(idx_name)
                if index.check_structure():
                    click.echo(f"✓ {idx_name}")
                    if verbose:
                        click.echo(
                            f"    {index.nb_partitions} partitions, {index.nb_samples} samples"
                        )
                else:
                    errors.append((idx_name, "Structure check failed"))
                    click.echo(f"✗ {idx_name}: Structure check failed", err=True)
            except Exception as e:
                errors.append((idx_name, str(e)))
                click.echo(f"✗ {idx_name}: {e}", err=True)

        click.echo()
        if errors:
            click.echo(
                f"Validation complete: {len(indices) - len(errors)} OK, {len(errors)} FAILED",
                err=True,
            )
            raise click.ClickException(
                f"Registry validation found {len(errors)} error(s)"
            )
        else:
            click.echo(f"Validation complete: All {len(indices)} indices OK")

    except Exception as e:
        if "Validation complete" in str(e):
            raise
        raise click.ClickException(f"Registry check failed: {e}")


@registry.command(name="remove")
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.option(
    "--index-id",
    "-n",
    required=True,
    help="Index ID to remove",
)
@click.option(
    "--delete-files",
    is_flag=True,
    help="Also delete index files from disk (destructive!)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def registry_remove(registry_path, index_id, delete_files, force):
    """Remove index from registry (optionally delete files)."""
    Main.init()

    try:
        registry = KmindexRegistry(registry_path)

        if not registry.has_index(index_id):
            raise click.ClickException(f"Index '{index_id}' not found in registry")

        # Confirm if not forced
        if not force:
            msg = f"Remove '{index_id}' from registry"
            if delete_files:
                msg += " and delete index files"
            msg += "?"

            if not click.confirm(msg):
                click.echo("Operation cancelled")
                return

        # Get index before removal (needed to delete files)
        index = registry.get_index(index_id)

        # Remove from registry
        registry.remove_index(index_id)
        click.echo(f"✓ Removed '{index_id}' from registry")

        # Delete files if requested
        if delete_files:
            try:
                index.destroy_entire_index()
                click.echo(f"✓ Deleted index files from disk")
            except Exception as e:
                click.echo(f"⚠ Failed to delete some files: {e}", err=True)

    except Exception as e:
        raise click.ClickException(f"Failed to remove index: {e}")


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

    Examples:
      # Compress all partitions with default settings
      kmhelpers compress -i ./indices -n my_index -o ./compressed

      # Compress specific partitions with size comparison
      kmhelpers compress -i ./indices -n my_index -o ./out -m 1 -m 2 -m 3 --compare-unordered

      # Custom block size with verification
      kmhelpers compress -i ./indices -n my_index -o ./out --block-size 16777216 --enable-check
    """
    Main.init()

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
    default=0,
    help="Z-value for kmindex (default: 0)",
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
    Main.init()

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


# ============================================================================
# PROJECT COMMANDS (High-level workflow using IndexBuilder/KmindexQuery)
# ============================================================================


def _get_project_config(project_path):
    """Load project configuration from .kmhelpers.yaml"""
    config_path = os.path.join(project_path, ".kmhelpers.yaml")
    if not os.path.exists(config_path):
        raise click.ClickException(
            f"Project not initialized. Run 'kmhelpers project create {project_path}' first"
        )
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise click.ClickException(f"Failed to load project config: {e}")


def _save_project_config(project_path, config):
    """Save project configuration to .kmhelpers.yaml"""
    config_path = os.path.join(project_path, ".kmhelpers.yaml")
    try:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        raise click.ClickException(f"Failed to save project config: {e}")


@cli.group()
def project():
    """Opinionated project workflow for building and querying indices."""
    pass


@project.command(name="create")
@click.argument("project_path", type=click.Path())
@click.option(
    "--k",
    "--kmer-size",
    "kmer_size",
    type=int,
    default=31,
    help="K-mer size (default: 31)",
)
@click.option(
    "--z",
    "--minim-size",
    "minim_size",
    type=int,
    default=6,
    help="Minimizer size (default: 6)",
)
def project_create(project_path, kmer_size, minim_size):
    """Initialize a new kmhelpers project."""
    Main.init()

    try:
        # Create base directory
        os.makedirs(project_path, exist_ok=True)

        # Create IndexBuilder to set up directory structure
        builder = IndexBuilder(project_path, k=kmer_size, z=minim_size)

        # Calculate s (span) from k and z: s = k - z + 1
        s = kmer_size - minim_size + 1

        # Create and save project metadata
        config = {
            "version": "1.0",
            "k": kmer_size,
            "z": minim_size,
            "s": s,
            "created": str(Path(project_path).absolute()),
        }
        _save_project_config(project_path, config)

        click.echo(f"✓ Project created: {project_path}")
        click.echo(f"  K-mer size (k): {kmer_size}")
        click.echo(f"  Minimizer size (z): {minim_size}")
        click.echo(f"  Span (s): {s}")
        click.echo(f"  Structure:")
        click.echo(f"    - registry/")
        click.echo(f"    - .subindexes/")
        click.echo(f"    - logs/")

    except Exception as e:
        raise click.ClickException(f"Failed to create project: {e}")


@project.command(name="build")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("index_name")
@click.option(
    "--fof",
    required=True,
    type=click.Path(exists=True, file_okay=True),
    help="Path to FOF file",
)
@click.option(
    "--bloom-size",
    type=int,
    required=True,
    help="Bloom filter size (bits)",
)
@click.option(
    "--assembled",
    is_flag=True,
    default=False,
    help="Mark index as assembled data",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=0,
    help="Number of threads (0 = auto-detect)",
)
@click.option(
    "--partitions",
    type=int,
    default=256,
    help="Number of partitions (default: 256)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt before building",
)
def project_build(
    project_path,
    index_name,
    fof,
    bloom_size,
    assembled,
    threads,
    partitions,
    verbose,
    force,
):
    """Build an index within the project."""
    Main.init()

    try:
        # Load project configuration
        config = _get_project_config(project_path)

        # Load FOF file into FofManager
        manager = FofManager()
        try:
            with open(fof, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 2:
                            sample_name, file_path = parts[0], parts[1]
                            manager.add_sample(file_path, sample_name)
        except Exception as e:
            raise click.ClickException(f"Failed to load FOF file: {e}")

        if verbose:
            click.echo(f"Building index '{index_name}' in project: {project_path}")
            click.echo(f"  Samples: {manager.get_sample_count()}")
            click.echo(f"  K-mer size: {config['k']}")

        # Show confirmation with size estimation (skip if -f/--force is used)
        if not force:
            click.echo()
            try:
                size_est = estimate_build_size(fof, bloom_size=bloom_size, nb_cell=None)
                click.echo("Build Size Estimate:")
                click.echo(
                    f"  Input data: {size_est['input_size_gb']:.2f} GB ({size_est['sample_count']} samples)"
                )
                click.echo(
                    f"  Estimated index size: {size_est['index_size_min_gb']:.2f} - {size_est['index_size_max_gb']:.2f} GB"
                )
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

        # Create IndexBuilder
        builder = IndexBuilder(project_path, k=config["k"], z=config["z"])

        # Build the subindex
        index = builder.create_subindex(
            name=index_name,
            samples=manager,
            assembled=assembled,
            bloom_size=bloom_size,
            n_partitions=partitions,
            n_threads=threads,
            auto_check=True,
        )

        click.echo(f"✓ Index built successfully")
        click.echo(f"  Index name: {index_name}")
        click.echo(f"  Samples: {index.nb_samples}")
        click.echo(f"  Partitions: {index.nb_partitions}")
        click.echo(f"  K-mer size: {index.kmer_size}")

    except Exception as e:
        raise click.ClickException(f"Failed to build index: {e}")


@project.command(name="query")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("index_name")
@click.option(
    "--query",
    "-q",
    required=True,
    type=click.Path(exists=True, file_okay=True),
    help="Path to query file (FASTA/FASTQ)",
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    default="query_results",
    type=click.Path(file_okay=False),
    help="Output directory (default: query_results)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="Number of threads",
)
@click.option(
    "--single-query",
    type=str,
    help="Single query mode (batch name)",
)
@click.option(
    "--aggregate",
    is_flag=True,
    default=False,
    help="Aggregate results across indices",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
def project_query(
    project_path,
    index_name,
    query,
    output_dir,
    threads,
    single_query,
    aggregate,
    verbose,
):
    """Query an index within the project."""
    Main.init()

    try:
        # Load project configuration
        config = _get_project_config(project_path)

        # Resolve registry path
        registry_path = os.path.join(project_path, "registry")
        if not os.path.exists(registry_path):
            raise click.ClickException(
                f"Registry not found in project: {registry_path}"
            )

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        if verbose:
            click.echo(f"Querying index '{index_name}' from project: {project_path}")
            click.echo(f"  Registry: {registry_path}")
            click.echo(f"  Query file: {query}")

        # Initialize KmindexQuery
        kquery = KmindexQuery(query)

        # Execute query
        results = kquery.execute(
            registry_path=registry_path,
            output_dir=output_dir,
            index_ids=[index_name],
            z=config["z"],
            single_query=single_query,
            aggregate=aggregate,
            threads=threads,
        )

        click.echo(f"✓ Query completed")
        click.echo(f"  Index: {index_name}")
        click.echo(f"  Results: {output_dir}")
        click.echo(f"  Query results found: {len(results)}")

        if verbose and results:
            for result in results:
                click.echo(f"    - {result}")

    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")


@project.command(name="info")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def project_info(project_path):
    """Show project information and indices."""
    Main.init()

    try:
        # Load project configuration
        config = _get_project_config(project_path)

        click.echo(f"Project: {project_path}")
        click.echo(f"  Version: {config.get('version', 'unknown')}")
        click.echo(f"  K-mer size (k): {config['k']}")
        click.echo(f"  Minimizer size (z): {config['z']}")
        click.echo(f"  Span (s): {config['s']}")
        click.echo()

        # Show directory structure
        click.echo("Project structure:")
        for subdir in ["registry", ".subindexes", "logs"]:
            dir_path = os.path.join(project_path, subdir)
            exists = "✓" if os.path.exists(dir_path) else "✗"
            click.echo(f"  {exists} {subdir}/")

        click.echo()

        # List indices in registry
        registry_path = os.path.join(project_path, "registry")
        if os.path.exists(registry_path):
            try:
                registry = KmindexRegistry(registry_path)
                indices = registry.list_indices()

                if indices:
                    click.echo(f"Registered indices ({len(indices)}):")
                    for idx_name in indices:
                        index = registry.get_index(idx_name)
                        click.echo(f"  {idx_name}")
                        click.echo(f"    - Samples: {index.nb_samples}")
                        click.echo(f"    - Partitions: {index.nb_partitions}")
                        click.echo(f"    - K-mer size: {index.kmer_size}")
                else:
                    click.echo("No indices registered yet")
            except Exception as e:
                click.echo(f"Error reading registry: {e}", err=True)
        else:
            click.echo("Registry not yet created")

    except Exception as e:
        raise click.ClickException(f"Failed to get project info: {e}")


if __name__ == "__main__":
    cli()
