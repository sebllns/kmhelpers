"""Merge-span command for renaming span identifiers in assembly index files."""

import logging
import os

import click
import yaml

logger = logging.getLogger(__name__)


def format_bytes(num_bytes):
    """Convert bytes to human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f}{unit}".rstrip("0").rstrip(".")
        num_bytes /= 1024.0
    return f"{num_bytes:.2f}PB"


@click.command(name="merge-span")
@click.argument("source_span")
@click.argument("target_span")
@click.option(
    "--index-dir",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to assembly index directory",
)
@click.option(
    "--db-name",
    required=True,
    help="Database name (e.g., tol_assembly)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def merge_span(source_span, target_span, index_dir, db_name, force):
    """Merge files from source span group into target span group.

    This command merges SOURCE_SPAN group to TARGET_SPAN group:
    - Opens the span registry and gets all files in source group
    - Renames and updates each file from source group to target group
    - Updates the keys inside each YAML file
    - Updates the registry file
    - Updates the main assembly YAML file
    """

    # source_span and target_span are group numbers (e.g., "27", "28")
    source_group = int(source_span)
    target_group = int(target_span)

    # Validate that target is greater than source
    if target_group <= source_group:
        raise click.ClickException(
            f"Target span group ({target_group}) must be greater than source span group ({source_group})"
        )

    # Open and read registry file
    registry_path = os.path.join(index_dir, f"{db_name}_span_registry.yaml")
    if not os.path.exists(registry_path):
        raise click.ClickException(f"Registry file not found: {registry_path}")

    with open(registry_path, "r") as f:
        registry = yaml.safe_load(f)

    if not registry or source_group not in registry:
        raise click.ClickException(
            f"Source span group '{source_group}' not found in registry"
        )

    # Get all files from source span group
    source_files = registry[source_group]
    if not source_files:
        raise click.ClickException(
            f"No files found for source span group '{source_group}'"
        )

    click.echo(
        f"Found {len(source_files)} file(s) in source span group '{source_group}':"
    )
    for f in source_files:
        click.echo(f"  - {f}")

    # Confirm if not forced
    if not force:
        click.echo(
            f"\nThis will merge all files from group {source_group} to group {target_group}"
        )
        if not click.confirm("Continue?"):
            click.echo("Operation cancelled")
            return

    try:
        # Track files to update in assembly
        assembly_updates = []

        # Initialize target group if it doesn't exist
        if target_group not in registry:
            raise click.ClickException(f"Target span not found'{source_group}'")

        # Open reference file (first file in target group)
        ref_filename = f"{db_name}_span_{target_group}_0.yaml"
        ref_path = os.path.join(index_dir, ref_filename)
        if not os.path.exists(ref_path):
            raise click.ClickException(f"Reference file not found: {ref_filename}")

        with open(ref_path, "r") as f:
            ref_data = yaml.safe_load(f)

        if not ref_data:
            raise click.ClickException(
                f"Reference file is empty or invalid: {ref_filename}"
            )

        # Extract reference file key and content
        ref_key = list(ref_data.keys())[0]
        ref_content = ref_data[ref_key]

        # Calculate starting index before processing
        starting_index = len(registry[target_group])

        # Process each entry file from source span group
        for idx, source_filename in enumerate(
            source_files[:]
        ):  # Copy list to avoid modification during iteration
            source_path = os.path.join(index_dir, source_filename)

            if not os.path.exists(source_path):
                click.echo(f"⚠ Source file not found (skipping): {source_filename}")
                continue

            # Generate target filename with new index
            # New index = starting index + current position in source files
            # e.g., tol_assembly_span_27_0.yaml -> tol_assembly_span_28_7.yaml (if 28 has 7 files)
            new_index = starting_index + idx
            target_filename = f"{db_name}_span_{target_group}_{new_index}.yaml"
            target_path = os.path.join(index_dir, target_filename)

            # Check if target already exists
            if os.path.exists(target_path):
                click.echo(
                    f"⚠ Target file already exists (skipping): {target_filename}"
                )
                continue

            # Read source YAML file
            with open(source_path, "r") as f:
                data = yaml.safe_load(f)

            if not data:
                click.echo(
                    f"⚠ Source file is empty or invalid YAML (skipping): {source_filename}"
                )
                continue

            # Update keys in the YAML file
            # Keys need to be updated from source group to target group with new index
            # e.g., tol_assembly_span_27_0 -> tol_assembly_span_28_7
            keys_to_update = list(data.keys())
            for old_key in keys_to_update:
                # Replace the group number and index in the key
                new_key = f"{db_name}_span_{target_group}_{new_index}"
                content = data.pop(old_key)

                # Update specific parameters from reference file
                if "parameters" in content and "parameters" in ref_content:
                    ref_params = ref_content.get("parameters", {})
                    content["parameters"]["partition_count"] = ref_params.get(
                        "partition_count"
                    )
                    content["parameters"]["bf_size"] = ref_params.get("bf_size")
                    content["parameters"]["parent_index"] = ref_filename

                # Update infos with scaled storage sizes
                if "infos" in content:
                    multiplier = 2 ** (target_group - source_group)
                    infos = content["infos"]

                    if "span" in infos:
                        infos["span"] = target_group

                    # Scale byte counts
                    if "total_stored_size_bytes" in infos:
                        total_bytes = int(infos["total_stored_size_bytes"])
                        scaled_total_bytes = total_bytes * multiplier
                        infos["total_stored_size_bytes"] = scaled_total_bytes
                        infos["total_stored_size_str"] = format_bytes(
                            scaled_total_bytes
                        )

                    if "partition_stored_size_bytes" in infos:
                        del infos["partition_stored_size_bytes"]
                        del infos["partition_stored_size_str"]
                        # partition_bytes = int(infos["partition_stored_size_bytes"])
                        # scaled_partition_bytes = partition_bytes * multiplier
                        # infos["partition_stored_size_bytes"] = scaled_partition_bytes
                        # infos["partition_stored_size_str"] = format_bytes(
                        #     scaled_partition_bytes
                        # )

                # Store the updated content
                data[new_key] = content
                assembly_updates.append((old_key, new_key))

            # Write to target file
            with open(target_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            click.echo(f"✓ Created {target_filename}")

            # Delete source file
            os.remove(source_path)
            click.echo(f"✓ Removed {source_filename}")

            # Add to target group registry
            if target_filename not in registry[target_group]:
                registry[target_group].append(target_filename)

        # Update registry - files are already added with new indices during processing
        # Just remove from source group
        if source_group in registry and source_group:
            registry[source_group].clear()

        # Remove empty groups
        if not registry[source_group]:
            del registry[source_group]

        with open(registry_path, "w") as f:
            yaml.dump(registry, f, default_flow_style=False, sort_keys=False)
        click.echo(f"✓ Updated registry")

        # Update main assembly file
        assembly_path = os.path.join(index_dir, f"{db_name}.yaml")
        if os.path.exists(assembly_path):
            with open(assembly_path, "r") as f:
                assembly = yaml.safe_load(f)

            if assembly:
                for old_key, new_key in assembly_updates:
                    if old_key in assembly:
                        assembly[new_key] = assembly.pop(old_key)

                with open(assembly_path, "w") as f:
                    yaml.dump(assembly, f, default_flow_style=False, sort_keys=False)
                click.echo(f"✓ Updated assembly file")

        click.echo(f"\n✓ Successfully merged group {source_group} -> {target_group}")

    except yaml.YAMLError as e:
        raise click.ClickException(f"YAML error: {e}")
    except Exception as e:
        raise click.ClickException(f"Failed to merge spans: {e}")
