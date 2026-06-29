"""Recursively list samples from a directory and output a JSONL file."""

import logging
import os

import click

from pykmhelpers.pipeline.sample_lister import SampleLister

logger = logging.getLogger(__name__)


@click.command(name="list")
@click.argument(
    "input_path",
    nargs=1,
    required=True,
    type=click.Path(exists=True),
)
@click.option(
    "--output",
    "-o",
    "output_file",
    required=True,
    type=click.Path(dir_okay=False),
    help="Path for the output JSONL file. If it already exists, it is backed up and the run resumes without reprocessing already-listed samples (use --autorename to rename duplicates instead of skipping).",
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
    "--data-type",
    "-t",
    "data_type",
    type=click.Choice(["a", "assembled", "u", "unassembled"], case_sensitive=False),
    default="a",
    show_default=True,
    help="Data type: a/assembled (default) or u/unassembled (raw reads)",
)
@click.option(
    "--no-count",
    "-nc",
    "no_count",
    is_flag=True,
    default=False,
    help="Skip k-mer counting with ntcard",
)
@click.option(
    "--leaf-grouping",
    "-lg",
    "leaf_grouping",
    is_flag=True,
    default=False,
    help="Group files by leaf folder; each leaf directory becomes one sample",
)
@click.option(
    "--autorename",
    "-r",
    is_flag=True,
    default=False,
    help="Rename duplicate sample IDs by appending a numeric suffix instead of skipping",
)
@click.option(
    "--ntcard-threads",
    "-ntt",
    "ntcard_threads",
    type=int,
    default=8,
    help="⚙️  Number of threads used by ntcard for k-mer counting (default: 8)",
)
def list_samples(
    input_path,
    output_file,
    kmer_size,
    data_type,
    no_count,
    leaf_grouping,
    autorename,
    ntcard_threads,
):
    """Scan a directory or import a sample list, count k-mers, and output a JSONL file.

    INPUT can be a directory (scanned recursively for sample files) or a
    plain-text / YAML file listing samples — the type is detected automatically.

    By default, each file is treated as its own sample. Use --leaf-grouping
    to group files by leaf folder, where each leaf directory becomes one
    sample whose ID is the folder name.

    K-mer counting is enabled by default. Use --no-count to skip it. If the
    output file already exists and is incomplete, the run will resume from
    where it left off without recounting already-finished samples.
    """
    is_assembled = data_type.lower() in ("a", "assembled")
    input_dir = input_path if os.path.isdir(input_path) else None
    input_list = input_path if os.path.isfile(input_path) else None
    try:
        SampleLister(
            output_file=output_file,
            input_dir=input_dir,
            input_list=input_list,
            kmer_size=kmer_size,
            is_assembled=is_assembled,
            do_count=not no_count,
            do_grouping=leaf_grouping,
            autorename=autorename,
            ntcard_threads=ntcard_threads,
        ).run()
        logger.info("SUCCESS ('list')")
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except (NotADirectoryError, ValueError) as e:
        raise click.UsageError(str(e))
