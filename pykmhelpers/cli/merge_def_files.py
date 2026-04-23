"""Merge definition files command."""

import logging

import click
import yaml

from .experimental import experimental

logger = logging.getLogger(__name__)


@experimental.command(name="merge-def-files")
@click.argument("file_1", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.argument("file_2", type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.argument("output", type=click.Path(file_okay=True, dir_okay=False))
def merge_def_files(file_1, file_2, output):
    """Merge two definition YAML files.

    Takes parameters from the file with the highest span (infos.span) and
    appends the samples lists together.
    """

    try:
        # Read both YAML files
        with open(file_1, "r") as f:
            data_1 = yaml.safe_load(f)

        with open(file_2, "r") as f:
            data_2 = yaml.safe_load(f)

        if not data_1 or not data_2:
            raise click.ClickException("One or both input files are empty or invalid")

        # Extract the main keys (should be single key per file)
        key_1 = list(data_1.keys())[0]
        key_2 = list(data_2.keys())[0]

        content_1 = data_1[key_1]
        content_2 = data_2[key_2]

        # Get spans from infos
        span_1 = content_1.get("infos", {}).get("span")
        span_2 = content_2.get("infos", {}).get("span")

        if span_1 is None or span_2 is None:
            raise click.ClickException("Both files must have 'infos.span' key defined")

        # Determine which has the highest span
        if span_1 >= span_2:
            highest_content = content_1
            highest_key = key_1
            highest_span = span_1
        else:
            highest_content = content_2
            highest_key = key_2
            highest_span = span_2

        click.echo(f"Using parameters from span {highest_span}")

        # Create merged content based on highest span
        merged_content = highest_content.copy()

        # Merge samples lists
        samples_1 = content_1.get("samples", [])
        samples_2 = content_2.get("samples", [])

        if samples_1 or samples_2:
            merged_samples = list(samples_1) + list(samples_2)
            merged_content["samples"] = merged_samples
            click.echo(
                f"✓ Merged {len(samples_1)} + {len(samples_2)} samples = {len(merged_samples)} total"
            )

        # Update infos section
        if "infos" in merged_content:
            infos = merged_content["infos"]

            # Update sample_count
            sample_count_1 = content_1.get("infos", {}).get("sample_count", 0)
            sample_count_2 = content_2.get("infos", {}).get("sample_count", 0)
            infos["sample_count"] = sample_count_1 + sample_count_2

            # Remove storage size keys
            infos.pop("total_stored_size_bytes", None)
            infos.pop("total_stored_size_str", None)
            infos.pop("partition_stored_size_bytes", None)
            infos.pop("partition_stored_size_str", None)

        # Write merged output
        merged_data = {highest_key: merged_content}
        with open(output, "w") as f:
            yaml.dump(merged_data, f, default_flow_style=False, sort_keys=False)

        click.echo(f"✓ Successfully merged files to {output}")

    except yaml.YAMLError as e:
        raise click.ClickException(f"YAML error: {e}")
    except Exception as e:
        raise click.ClickException(f"Failed to merge definition files: {e}")
