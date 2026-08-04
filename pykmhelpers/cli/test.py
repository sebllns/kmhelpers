"""Test data generation commands."""

import json
import math
import os
import random
from datetime import datetime

import click
import yaml

from pykmhelpers.core import KmindexRegistry, KmtricksIndex
from pykmhelpers.core.fasta import Fasta, FASTAReader
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.sample_lister import SampleLister

# Guard against a stddev given in kmer counts instead of spans
MAX_SPAN_STDDEV: float = 64.0


@click.group()
def test():
    """Test data generation and utilities for testing and benchmarking."""
    pass


@test.command(name="create-fasta")
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for test FASTA files",
)
@click.option(
    "--n-samples",
    "-n",
    type=int,
    default=5,
    help="Number of random sequences to generate (default: 5)",
)
@click.option(
    "--average-size",
    "-a",
    type=int,
    default=1000,
    help="Average sequence size in bases (default: 1000)",
)
@click.option(
    "--min-size",
    "-m",
    type=int,
    default=100,
    help="Minimum sequence size in bases (default: 100)",
)
@click.option(
    "--create-fof",
    is_flag=True,
    default=False,
    help="Also create a FOF file listing the generated FASTA files",
)
def test_create_fasta(output_dir, n_samples, average_size, min_size, create_fof):
    """Generate random FASTA test data for testing and benchmarking.

    Creates random sequences and optionally generates a FOF file to use them.

    Examples:
      # Generate 10 sequences with default sizes
      kmhelpers test create-fasta -o ./test_data -n 10

      # Generate with custom size parameters
      kmhelpers test create-fasta -o ./test_data -n 20 -a 5000 -m 500

      # Generate test data and create a FOF file automatically
      kmhelpers test create-fasta -o ./test_data -n 5 --create-fof
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        click.echo(f"Generating {n_samples} random FASTA sequences...")
        click.echo(f"  Output directory: {output_dir}")
        click.echo(f"  Average size: {average_size} bp")
        click.echo(f"  Minimum size: {min_size} bp")

        # Create random test dataset
        Fasta.create_random_test_dataset(
            output_dir=output_dir,
            n_samples=n_samples,
            average_size=average_size,
            min_size=min_size,
        )

        click.echo(f"✓ Generated {n_samples} FASTA files in {output_dir}")

        # Optionally create FOF file
        if create_fof:
            fof_path = os.path.join(output_dir, "sequences.fof")
            manager = FofManager()

            # Add all generated FASTA files to FOF
            for i in range(n_samples):
                fasta_file = os.path.realpath(
                    os.path.join(output_dir, f"sequence_{i}.fasta")
                )
                sample_name = f"sequence_{i}"
                manager.add_sample([fasta_file], sample_name)

            manager.save(fof_path)
            click.echo(f"✓ Created FOF file: {fof_path}")
            click.echo(f"  Samples: {manager.get_sample_count()}")

    except Exception as e:
        raise click.ClickException(f"Failed to create test data: {e}")


@test.command(name="create-db")
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for test database",
)
@click.option(
    "--n-samples",
    "-n",
    type=int,
    default=5,
    help="Number of samples to generate (default: 5)",
)
@click.option(
    "--average-size",
    "-a",
    type=int,
    default=1000,
    help="Average sequence size in bases (default: 1000)",
)
@click.option(
    "--min-size",
    "-m",
    type=int,
    default=100,
    help="Minimum sequence size in bases (default: 100)",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    help="K-mer size for counting distinct k-mers (default: 25)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
def test_create_db(output_dir, n_samples, average_size, min_size, kmer_size, verbose):
    """Generate test database with sample sequences and k-mer statistics.

    Creates n random sequences with varying sizes and tracks distinct k-mer counts.
    Outputs FASTA files and a samples.yaml metadata file.

    Examples:
      # Generate 10 samples with default sizes
      kmhelpers test create-db -o ./test_db -n 10

      # Generate with custom size and k-mer parameters
      kmhelpers test create-db -o ./test_db -n 20 -a 5000 -m 500 -k 31

      # Generate with verbose output
      kmhelpers test create-db -o ./test_db -n 5 -v
    """
    try:
        # Validate parameters
        if min_size > average_size:
            raise click.BadParameter(
                f"min-size ({min_size}) cannot be greater than average-size ({average_size})"
            )

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        click.echo(f"Generating test database with {n_samples} samples...")
        click.echo(f"  Output directory: {output_dir}")
        click.echo(f"  Average size: {average_size} bp")
        click.echo(f"  Minimum size: {min_size} bp")
        click.echo(f"  K-mer size: {kmer_size}")

        # Prepare metadata
        metadata = {
            "description": "generated by kmhelpers",
            "date": datetime.now().isoformat(),
            "total_samples": n_samples,
            "k": kmer_size,
            "samples": {},
        }
        padding_width = len(str(n_samples - 1))
        # Generate samples
        for i in range(n_samples):
            sample_id = f"sample_{str(i).zfill(padding_width)}"

            # Generate random size between min_size and average_size
            size = random.randint(min_size, average_size)

            # Create sequence and count distinct k-mers
            seq = Sequence(header=sample_id)
            kmer_count = seq.fill_random_and_count_kmers(length=size, k=kmer_size)

            # Save FASTA file
            fasta_path = os.path.join(output_dir, f"{sample_id}.fasta")
            with open(fasta_path, "w") as f:
                f.write(seq.to_fasta())

            # Add to metadata
            metadata["samples"][sample_id] = {
                "kmer_count": kmer_count,
                "files": [fasta_path],
            }

            if verbose:
                click.echo(
                    f"  Generated {sample_id}: {size} bp, {kmer_count} distinct {kmer_size}-mers"
                )

        # Save metadata to YAML
        metadata_path = os.path.join(output_dir, "../samples.yaml")
        with open(metadata_path, "w") as f:
            yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)

        click.echo(f"✓ Test database created successfully")
        click.echo(f"  Samples: {n_samples}")
        click.echo(f"  Metadata: {metadata_path}")
        click.echo(f"  FASTA files: {output_dir}/*.fasta")

    except click.BadParameter:
        raise
    except Exception as e:
        raise click.ClickException(f"Failed to create test database: {e}")


@test.command(name="create-list")
@click.option(
    "--output",
    "-o",
    "output_file",
    required=True,
    type=click.Path(dir_okay=False),
    help="Path for the output JSONL file",
)
@click.option(
    "--n-samples",
    "-n",
    type=int,
    default=1000,
    show_default=True,
    help="Number of fake samples to generate",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    show_default=True,
    help="K-mer size reported in the header",
)
@click.option(
    "--median",
    "-mu",
    "median",
    type=float,
    default=500000000.0,
    show_default=True,
    help="Median kmer_count (center of the lognormal distribution)",
)
@click.option(
    "--stddev",
    "-sd",
    type=float,
    default=3.0,
    show_default=True,
    help="Standard deviation in spans, i.e. in log2(kmer_count) units",
)
@click.option(
    "--root-path",
    "-r",
    default=".",
    show_default=True,
    help="Value written as root_path in the header",
)
@click.option(
    "--prefix",
    "-p",
    default="data",
    show_default=True,
    help="Sample name prefix",
)
@click.option(
    "--data-type",
    "-dt",
    type=click.Choice(["a", "assembled", "u", "unassembled"], case_sensitive=False),
    default="a",
    show_default=True,
    help="Data type: a/assembled (default) or u/unassembled",
)
@click.option(
    "--seed",
    "-s",
    type=int,
    default=None,
    help="Random seed for reproducible output",
)
def test_create_list(
    output_file,
    n_samples,
    kmer_size,
    median,
    stddev,
    root_path,
    prefix,
    data_type,
    seed,
):
    """Generate a fake JSONL sample list, as produced by the 'list' command.

    No FASTA file is created: only the manifest, with kmer_count values drawn
    from a lognormal distribution: log2(kmer_count) ~ N(log2(median), stddev).
    Spans being logarithmic, stddev is expressed in spans, so the resulting
    span distribution is a bell curve centered on log2(median).

    Examples:
      # 100 samples, k=31, median 50000 kmers, spread of 2 spans
      kmhelpers test create-list -o fake.jsonl -n 100 -k 31 -mu 50000 -sd 2

      # Reproducible unassembled list
      kmhelpers test create-list -o fake.jsonl -n 20 -dt u --seed 42
    """
    if n_samples < 1:
        raise click.BadParameter(f"n-samples ({n_samples}) must be >= 1")
    if median < 1:
        raise click.BadParameter(f"median ({median}) must be >= 1")
    if stddev < 0:
        raise click.BadParameter(f"stddev ({stddev}) must be >= 0")
    if stddev > MAX_SPAN_STDDEV:
        raise click.BadParameter(
            f"stddev ({stddev}) must be <= {MAX_SPAN_STDDEV}: it is expressed "
            "in spans (log2 units), not in kmer counts"
        )

    mu = math.log2(median)

    if seed is not None:
        random.seed(seed)

    is_assembled = data_type.lower() in ("a", "assembled")
    root = os.path.realpath(root_path)
    padding_width = len(str(n_samples - 1))

    try:
        with open(output_file, "w") as out:
            # Reuse the 'list' header layout, but flag the data as fake
            header = json.loads(
                SampleLister._new_header(
                    root, kmer_size, is_assembled, 1 if is_assembled else 2
                )
            )
            header["description"] = "Fake list generated by kmhelpers test create-list"
            out.write(json.dumps(header) + "\n")
            for i in range(n_samples):
                name = f"{prefix}_{str(i).zfill(padding_width)}"
                entry = {
                    "name": name,
                    "files": [f"{name}.fasta"],
                    "kmer_count": max(1, round(2 ** random.gauss(mu, stddev))),
                }
                out.write(json.dumps(entry) + "\n")
    except OSError as e:
        raise click.ClickException(f"Failed to write sample list: {e}")

    click.echo(f"✓ Generated {n_samples} fake samples in {output_file}")
    click.echo(f"  log2(kmer_count) ~ N({mu:.2f}, {stddev}), median {round(median)}")


def _create_single_dataset(
    idx: KmtricksIndex,
    output_dir: str,
    n_samples: int,
    average_size,
    min_size,
):
    """
    Create test dataset by extracting sequences from the index.

    :param idx: The kmtricks index to extract sequences from
    :type idx: KmtricksIndex
    :param output_dir: Output directory for test FASTA files
    :type output_dir: str
    :param n_samples: Number of samples to extract
    :type n_samples: int
    """
    os.makedirs(output_dir, exist_ok=True)
    fof = FofManager(idx.fof_path)
    samples = random.sample(idx.samples, min(n_samples, idx.nb_samples))
    for s in samples:
        p = fof.get_sample_paths(s)
        if not p:
            raise click.ClickException(f"No path for {s}")
        path = p[0]
        if path and os.path.isfile(path):
            try:
                reader = FASTAReader(path)
                output_file = os.path.join(output_dir, f"{s}.fasta")
                with open(output_file, "w") as f:
                    max_length = random.randint(min_size, average_size)
                    f.write(reader.fetch_first_n(max_length).to_fasta())
            except Exception as e:
                print(f"Failed to extract sequences from {path}: {str(e)}")


@test.command(name="extract-dataset")
@click.option(
    "--registry-path",
    "-r",
    default=".",
    type=click.Path(file_okay=False, dir_okay=True, exists=True, readable=True),
    help="Path to kmindex registry",
)
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory for test database",
)
@click.option(
    "--n-samples",
    "-n",
    type=int,
    default=5,
    help="Number of sequences to extract per sub-index (default: 5)",
)
@click.option(
    "--average-size",
    "-a",
    type=int,
    default=1000,
    help="Average sequence size in bases (default: 1000)",
)
@click.option(
    "--min-size",
    "-m",
    type=int,
    default=100,
    help="Minimum sequence size in bases (default: 100)",
)
def extract_dataset(registry_path, output_dir, n_samples, average_size, min_size):
    try:
        kreg = KmindexRegistry(registry_path, auto_create=False)
        for i in kreg:
            try:
                print(f"Extract sequences from {i.id}...")
                _create_single_dataset(
                    i, os.path.join(output_dir, i.id), n_samples, average_size, min_size
                )
            except Exception as e:
                print(f"Failed to extract sequences from {i.id}: {str(e)}")
    except Exception as e:
        raise click.ClickException(f"Failed to create test database: {e}")
