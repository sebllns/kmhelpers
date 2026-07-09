"""Count k-mers in sequence files using ntcard."""

import click
from pykmhelpers.core.kmer import KmerCounter


@click.command(name="count-kmers")
@click.option(
    "--input-file",
    "-i",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Input sequence file (FASTA, FASTQ, SAM, or BAM format)",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=31,
    help="K-mer size (default: 31)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=8,
    help="Number of threads (default: 8)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def count_kmers(input_file, kmer_size, threads, verbose):
    """Count the number of distinct k-mers in a sequence file using ntcard."""
    try:
        if verbose:
            click.echo(f"Counting {kmer_size}-mers in {input_file} using {threads} threads...")

        counter = KmerCounter(k=kmer_size, thread_count=threads)
        f1_value = counter.count(input_file)

        click.echo(f"k={kmer_size}\tF1\t{f1_value}")

    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))
