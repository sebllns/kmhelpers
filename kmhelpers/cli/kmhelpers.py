#!/usr/bin/env python3

import os
import click
from kmhelpers.core import utils as kmhelpers


@click.group()
def cli():
    """kmhelpers - A toolkit for managing, compressing, and querying k-mer indices."""
    pass


# ============================================================================
# REGISTER COMMANDS
# ============================================================================

@cli.group()
def register():
    """Register indices in a kmindex registry."""
    pass


@register.command(name="index")
@click.option(
    "--input",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing index folders",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory (where to create/update registry)",
)
@click.option(
    "--index",
    multiple=True,
    required=True,
    help="Index ID(s) to register (can specify multiple)",
)
def register_index(input, output, index):
    """Register individual indices in the registry."""
    kmhelpers.Main.init()

    # Create output directory
    os.makedirs(output, exist_ok=True)

    index_json_path = kmhelpers.Kmindex.get_json_path(output)
    if not os.path.isfile(index_json_path):
        kmhelpers.Kmindex.create_empty_index_json(output)

    # Validate input arguments
    if not os.path.isdir(input):
        raise click.BadParameter(f"Input path {input} is not a directory")

    if not os.path.isfile(index_json_path):
        raise click.BadParameter(f"JSON path {index_json_path} is not a file")
    if not (os.access(index_json_path, os.R_OK) and os.access(index_json_path, os.W_OK)):
        raise click.BadParameter(f"JSON file {index_json_path} is not readable/writable")

    index_ids = kmhelpers.Kmindex.read_index_ids_from_json(index_json_path)

    if not os.path.isdir(output):
        raise click.BadParameter(f"Output path {output} is not a directory")
    if not os.access(output, os.W_OK):
        raise click.BadParameter(f"Output directory {output} is not writable")

    for index_id in index:
        if index_id in index_ids:
            click.echo(f"Index {index_id} already registered, skipping...")
            continue
        click.echo(f"Registering index {index_id}...")
        kmhelpers.Kmindex.register_index_in_json(input, output, index_id)
        click.echo(f"Successfully registered {index_id}")


@register.command(name="directory")
@click.option(
    "-i",
    "--input-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to directory containing kmtricks indexes",
)
@click.option(
    "-o",
    "--output",
    default="kmindex-registry",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output kmindex registry path (created if doesn't exist)",
)
def register_directory(input_dir, output):
    """Create or update registry from a directory of kmtricks indices."""
    from kmhelpers.core.index import KmindexRegistry, KmtricksIndex

    # Initialize kmhelpers environment
    click.echo("Initializing kmhelpers...")
    kmhelpers.Main.init()
    click.echo(f"kmindex version: {kmhelpers.Kmindex.version()}")

    registry = KmindexRegistry(output)

    # Loop over all directories in the input folder
    for index_id in os.listdir(input_dir):
        entry_path = os.path.join(input_dir, index_id)

        # Skip if not a directory
        if not os.path.isdir(entry_path):
            continue

        try:
            # Load index
            index = KmtricksIndex(input_dir, index_id)
            index.load_kmtricks_index()
            if index.check_structure():
                click.echo(f"Found index: {index}")
                if registry.add_index(index):
                    click.echo(f"Registered {index.index_id} in {registry.json_path}")
                else:
                    click.echo(f"Index {index.index_id} already exists in registry")
        except Exception as e:
            click.echo(f"Error processing {index_id}: {e}", err=True)
            continue

    click.echo("---------------------------------------------------")
    click.echo("Registry summary:")
    click.echo(f"Available indices: {len(registry)} total")
    for idx in registry:
        click.echo(f"  - {idx}")
    click.echo("---------------------------------------------------")


# ============================================================================
# QUERY COMMAND
# ============================================================================

@cli.command()
@click.option(
    "--input",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Directory containing index registry (index.json)",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for query results",
)
@click.option(
    "--index",
    multiple=True,
    required=True,
    help="Index ID(s) to query (can specify multiple)",
)
@click.option(
    "--query",
    multiple=True,
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Query file(s) in FASTA/FASTQ format (can specify multiple)",
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
    help="Threshold for kmindex (default: 0.0)",
)
@click.option(
    "--compressed",
    is_flag=True,
    help="Use compressed index variant",
)
@click.option(
    "--report",
    default="report.json",
    help="Performance report filename (default: report.json)",
)
def query(input, output, index, query, zvalue, threshold, compressed, report):
    """Query indices with FASTA/FASTQ files."""
    kmhelpers.Main.init()

    index_json_path = os.path.join(input, "index.json")

    # Validate input arguments
    if not os.path.isdir(input):
        raise click.BadParameter(f"Input path {input} is not a directory")

    if not os.path.isfile(index_json_path):
        raise click.BadParameter(f"JSON path {index_json_path} is not a file")
    if not os.access(index_json_path, os.R_OK):
        raise click.BadParameter(f"JSON file {index_json_path} is not readable")

    index_ids = kmhelpers.Kmindex.read_index_ids_from_json(index_json_path)
    if len(index_ids) == 0:
        raise click.BadParameter(f"No index IDs found in {index_json_path}")

    click.echo(f"Found {len(index_ids)} index IDs in {index_json_path}")
    click.echo(f"Index IDs: {', '.join(index_ids)}")

    kmhelpers.Kmindex.validate_index_ids(index, index_ids)

    os.makedirs(output, exist_ok=True)

    for query_file in query:
        if not os.path.isfile(query_file):
            raise click.BadParameter(f"Query file {query_file} is not a file")
        if not os.access(query_file, os.R_OK):
            raise click.BadParameter(f"Query file {query_file} is not readable")

        click.echo(f"Processing query file {query_file}...")

        query_output = os.path.join(
            output, os.path.splitext(os.path.basename(query_file))[0]
        )

        if os.path.isdir(query_output):
            click.echo(f"Directory found: {query_output}. Skipping query...")
            continue

        result = kmhelpers.Kmindex.query_index(
            index,
            input,
            query_output,
            format="json",
            fastx=query_file,
            zvalue=zvalue,
            threshold=threshold,
            is_compressed=compressed,
        )

        if result is None:
            raise click.ClickException(f"Query command failed for {query_file}")

        km_output, km_monitor = result

        if not os.path.isdir(query_output):
            raise click.ClickException(f"Result directory not found: {query_output}")

        with open(os.path.join(query_output, ".cmd_output.log"), "w") as f:
            f.write(km_output)

        kmhelpers.Toolbox.json_serialize(
            km_monitor, os.path.join(query_output, report)
        )

        click.echo(f"Query output: {query_output}")


if __name__ == "__main__":
    cli()
