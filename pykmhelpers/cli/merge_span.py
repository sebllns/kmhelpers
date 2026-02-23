"""Merge-span command for renaming span identifiers in assembly index files."""

import logging
import os
import yaml
import click

logger = logging.getLogger(__name__)


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
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def merge_span(source_span, target_span, index_dir, force):
    """Rename a span identifier and update all corresponding files.

    This command renames SOURCE_SPAN to TARGET_SPAN across all assembly index files:
    - Renames the YAML file
    - Updates the key inside the YAML file
    - Updates the registry file
    - Updates the main assembly YAML file
    """

    # Validate span identifiers format
    source_filename = f"tol_assembly_span_{source_span}.yaml"
    target_filename = f"tol_assembly_span_{target_span}.yaml"

    source_path = os.path.join(index_dir, source_filename)
    target_path = os.path.join(index_dir, target_filename)

    # Check if source file exists
    if not os.path.exists(source_path):
        raise click.ClickException(f"Source span file not found: {source_filename}")

    # Check if target already exists
    if os.path.exists(target_path):
        raise click.ClickException(f"Target span file already exists: {target_filename}")

    # Confirm if not forced
    if not force:
        click.echo(f"This will rename:")
        click.echo(f"  {source_filename} -> {target_filename}")
        if not click.confirm("Continue?"):
            click.echo("Operation cancelled")
            return

    try:
        # Read source YAML file
        with open(source_path, 'r') as f:
            data = yaml.safe_load(f)

        if not data:
            raise click.ClickException(f"Source file is empty or invalid YAML")

        # The file should have a single key with the old span name
        old_key = f"tol_assembly_span_{source_span}"
        if old_key not in data:
            raise click.ClickException(f"Expected key '{old_key}' not found in source file")

        # Update the key
        new_key = f"tol_assembly_span_{target_span}"
        data[new_key] = data.pop(old_key)

        # Write to target file
        with open(target_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        click.echo(f"✓ Created {target_filename}")

        # Delete source file
        os.remove(source_path)
        click.echo(f"✓ Removed {source_filename}")

        # Update registry file
        registry_path = os.path.join(index_dir, "tol_assembly_span_registry.yaml")
        if os.path.exists(registry_path):
            with open(registry_path, 'r') as f:
                registry = yaml.safe_load(f)

            if registry:
                # Parse source and target spans to get the group number and index
                # Format is "XX_Y" where XX is the group and Y is the index
                parts = source_span.split('_')
                if len(parts) == 2:
                    group, source_idx = parts
                    target_parts = target_span.split('_')
                    if len(target_parts) == 2:
                        target_group, target_idx = target_parts

                        # Update registry entry
                        if group in registry:
                            if source_filename in registry[group]:
                                registry[group].remove(source_filename)
                                click.echo(f"✓ Removed from registry group {group}")

                        if target_group not in registry:
                            registry[target_group] = []
                        if target_filename not in registry[target_group]:
                            registry[target_group].append(target_filename)
                            click.echo(f"✓ Added to registry group {target_group}")

                        with open(registry_path, 'w') as f:
                            yaml.dump(registry, f, default_flow_style=False, sort_keys=False)
                        click.echo(f"✓ Updated {os.path.basename(registry_path)}")

        # Update main assembly file
        assembly_path = os.path.join(index_dir, "tol_assembly.yaml")
        if os.path.exists(assembly_path):
            with open(assembly_path, 'r') as f:
                assembly = yaml.safe_load(f)

            if assembly and old_key in assembly:
                assembly[new_key] = assembly.pop(old_key)
                with open(assembly_path, 'w') as f:
                    yaml.dump(assembly, f, default_flow_style=False, sort_keys=False)
                click.echo(f"✓ Updated {os.path.basename(assembly_path)}")

        click.echo(f"\n✓ Successfully merged {source_span} -> {target_span}")

    except yaml.YAMLError as e:
        raise click.ClickException(f"YAML error: {e}")
    except Exception as e:
        raise click.ClickException(f"Failed to merge spans: {e}")