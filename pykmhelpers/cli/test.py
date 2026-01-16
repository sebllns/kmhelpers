"""Test data generation commands."""

import os
import random
import yaml
import click
from datetime import datetime
from pykmhelpers.operations.fasta import Fasta
from pykmhelpers.operations.sequence import Sequence
from pykmhelpers.operations.fof import FofManager


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
                manager.add_sample(fasta_file, sample_name)

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

        # Generate samples
        for i in range(n_samples):
            sample_id = f"sample_{i}"

            # Generate random size between min_size and average_size
            size = random.randint(min_size, average_size)

            # Create sequence and count distinct k-mers
            seq = Sequence(header=sample_id)
            kmer_count = seq.fill_random_and_count_kmers(L=size, k=kmer_size)

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
        metadata_path = os.path.join(output_dir, "samples.yaml")
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
