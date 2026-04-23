"""FOF (File-of-Files) management commands."""

import json
import os

import click

from pykmhelpers.operations.fof_validation import FofValidator
from pykmhelpers.pipeline.fof import FofManager


@click.group()
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
    "-x",
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
            sample_name = manager.extract_sample_name(file_path)
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
            p = manager.get_sample_paths(sample_id)
            if not p:
                raise click.ClickException(f"No path for {sample_id}")
            for file_path in p:
                if not os.path.isfile(file_path):
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
                    {"id": sid, "path": manager.get_sample_paths(sid)}
                    for sid in sample_ids
                ],
            }
            click.echo(json.dumps(data, indent=2))
        else:
            # Output as table
            click.echo(f"FOF File: {fof_file}")
            click.echo(f"Samples: {len(sample_ids)}\n")

            for sample_id in sample_ids:
                file_path = manager.get_sample_paths(sample_id)
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
            sample_id = manager.extract_sample_name(sample_file)

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
