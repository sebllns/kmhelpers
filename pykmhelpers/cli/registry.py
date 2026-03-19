"""K-mer index registry management commands."""

import json
import os
import shutil

import click

from pykmhelpers import Kmindex, KmindexRegistry, KmtricksIndex


@click.group()
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.pass_context
def registry(ctx, registry_path):
    """Manage k-mer index registries."""
    ctx.ensure_object(dict)
    ctx.obj["registry_path"] = registry_path


@registry.command(name="add")
@click.option(
    "--input-dir",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory containing kmtricks indices",
)
@click.option(
    "--index-ids",
    "-n",
    multiple=True,
    help="Specific index IDs to register (register all if not specified)",
)
@click.pass_obj
def registry_add(obj, input_dir, index_ids):
    """Register kmtricks indices in a registry."""
    registry_path = obj["registry_path"]

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
@click.pass_obj
def registry_list(obj):
    """List all indices in a registry."""
    registry_path = obj["registry_path"]

    registry = KmindexRegistry(registry_path)

    indices = registry.list_indices()
    if not indices:
        click.echo("No indices found in registry")
        return

    click.echo(f"Registry: {registry_path}")
    click.echo(f"Available indices ({len(indices)} total):")
    for idx_name in indices:
        try:
            idx = registry.get_index(idx_name)
            click.echo(
                f"  • {idx_name} ({idx.nb_samples} samples, {idx.nb_partitions} partitions, k={idx.kmer_size})"
            )
        except Exception as e:
            click.echo(f"  ✗ {idx_name}: {e}", err=True)


@registry.command(name="info")
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
@click.pass_obj
def registry_info(obj, index_id, output_json):
    """Show detailed information about an index."""
    registry_path = obj["registry_path"]

    try:
        registry = KmindexRegistry(registry_path)

        if not registry.has_index(index_id):
            raise click.ClickException(f"Index '{index_id}' not found in registry")

        index = registry.get_index(index_id)

        if output_json:
            # Output as JSON
            data = {
                "index_id": index.id,
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
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed validation output",
)
@click.pass_obj
def registry_check(obj, verbose):
    """Validate registry consistency and check all index structures."""
    registry_path = obj["registry_path"]

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
@click.pass_obj
def registry_remove(obj, index_id, delete_files, force):
    """Remove index from registry (optionally delete files)."""
    registry_path = obj["registry_path"]

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
        registry.remove_index(index_id, delete_files=True)
        click.echo(f"✓ Removed '{index_id}' from registry")

    except Exception as e:
        raise click.ClickException(f"Failed to remove index: {e}")


@registry.command(name="rename")
@click.option(
    "--from",
    "-f",
    "index_id",
    required=True,
    help="Index ID to rename",
)
@click.option(
    "--to",
    "-t",
    "new_index_id",
    required=True,
    help="New index ID",
)
@click.pass_obj
def registry_rename(obj, index_id, new_index_id):
    """Rename an index"""
    registry_path = obj["registry_path"]

    try:
        registry = KmindexRegistry(registry_path)

        if not registry.has_index(index_id):
            raise click.ClickException(f"Index '{index_id}' not found in registry")

        # Get index before removal (needed to delete files)
        index = registry.get_index(index_id)

        if not registry.rename_index(index_id, new_index_id):
            raise click.ClickException(
                f"Could not rename index from '{new_index_id}' to '{index_id}'."
            )

        click.echo(f"✓ Renamed '{index_id}' to {new_index_id}")

    except Exception as e:
        raise click.ClickException(f"Failed to remove index: {e}")
