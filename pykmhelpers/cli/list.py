"""Recursively list samples from a directory and output a YAML file."""

import os
from datetime import datetime, timezone

import click
import yaml

from pykmhelpers.core.constants import DATA_EXTENSIONS
from pykmhelpers.core.kmer import KmerCounter
from pykmhelpers.pipeline.index_db import IndexDefinitionTools


def _find_data_files(path: str) -> list[str]:
    """Return all data files under path matching DATA_EXTENSIONS."""
    matches = []
    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False):
            name = entry.name
            for ext in DATA_EXTENSIONS:
                if name.endswith(ext):
                    matches.append(entry.path)
                    break
    return sorted(matches)


def _collect_samples_grouped(root: str) -> dict[str, list[str]]:
    """Recursively collect samples grouped by leaf folder."""
    samples: dict[str, list[str]] = {}
    tools = IndexDefinitionTools()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        # Leaf folder: no subdirectories contain data files
        # We consider a folder a leaf when it directly contains data files
        data_files = []
        for fname in sorted(filenames):
            for ext in DATA_EXTENSIONS:
                if fname.endswith(ext):
                    data_files.append(os.path.join(dirpath, fname))
                    break

        if data_files:
            folder_name = os.path.basename(dirpath)
            sample_id = tools.clean_sample_id(folder_name)
            if sample_id in samples:
                # Merge files if the same cleaned ID appears in multiple folders
                samples[sample_id].extend(data_files)
            else:
                samples[sample_id] = data_files

    return samples


def _collect_samples_flat(root: str) -> dict[str, list[str]]:
    """Collect all data files under root as individual samples (no grouping)."""
    tools = IndexDefinitionTools()
    samples: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fname in sorted(filenames):
            for ext in DATA_EXTENSIONS:
                if fname.endswith(ext):
                    filepath = os.path.join(dirpath, fname)
                    # Use filename without extensions as sample id
                    base = fname
                    for e in DATA_EXTENSIONS:
                        if base.endswith(e):
                            base = base[: len(base) - len(e)]
                            break
                    sample_id = tools.clean_sample_id(base)
                    if sample_id in samples:
                        samples[sample_id].append(filepath)
                    else:
                        samples[sample_id] = [filepath]
                    break

    return samples


@click.command(name="list")
@click.option(
    "--input",
    "-i",
    "input_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory to scan recursively for sample files",
)
@click.option(
    "--output",
    "-o",
    "output_file",
    required=True,
    type=click.Path(file_okay=True, dir_okay=False),
    help="Output YAML file path",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    show_default=True,
    help="K-mer size used for counting",
)
@click.option(
    "--count",
    "do_count",
    is_flag=True,
    default=False,
    help="Count k-mers for each sample using ntcard",
)
@click.option(
    "--no-grouping",
    "no_grouping",
    is_flag=True,
    default=False,
    help="Disable grouping by leaf folder; each file becomes its own sample",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=8,
    show_default=True,
    help="Number of threads for k-mer counting (only used with --count)",
)
def list_samples(input_dir, output_file, kmer_size, do_count, no_grouping, threads):
    """Recursively list samples from a directory and output a YAML file.

    By default, files are grouped by leaf folder: each leaf directory
    becomes one sample whose ID is the folder name. Use --no-grouping to
    treat every file independently.
    """
    input_dir = os.path.abspath(input_dir)

    if no_grouping:
        samples = _collect_samples_flat(input_dir)
    else:
        samples = _collect_samples_grouped(input_dir)

    if not samples:
        raise click.ClickException(f"No data files found under {input_dir}")

    counter = None
    if do_count:
        try:
            counter = KmerCounter(k=kmer_size, threadCount=threads)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))

    samples_out: dict = {}
    for sample_id in sorted(samples.keys()):
        files = samples[sample_id]
        kmer_count = 0
        if counter is not None:
            try:
                kmer_count = counter.count_files(files)
            except Exception as e:
                click.echo(f"Warning: could not count k-mers for {sample_id}: {e}", err=True)

        # Store paths relative to input_dir when possible
        rel_files = []
        for f in files:
            try:
                rel_files.append(os.path.relpath(f, start=os.path.dirname(input_dir)))
            except ValueError:
                rel_files.append(f)

        entry: dict = {"files": rel_files}
        if do_count:
            entry = {"kmer_count": kmer_count, "files": rel_files}

        samples_out[sample_id] = entry

    doc = {
        "description": "generated by kmhelpers",
        "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        "total_samples": len(samples_out),
        "k": kmer_size,
        "samples": samples_out,
    }

    with open(output_file, "w") as fh:
        yaml.dump(doc, fh, default_flow_style=False, sort_keys=False)

    click.echo(f"Listed {len(samples_out)} samples -> {output_file}")
