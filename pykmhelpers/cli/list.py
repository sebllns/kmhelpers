"""Recursively list samples from a directory and output a JSONL file."""

import logging

import click

from pykmhelpers.pipeline.sample_lister import SampleLister

logger = logging.getLogger(__name__)


@click.command(name="list")
@click.argument(
    "output_file",
    nargs=1,
    required=True,
    type=click.Path(dir_okay=False),
)
@click.option(
    "--input",
    "-i",
    "input_dir",
    required=False,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory to scan recursively for sample files",
)
@click.option(
    "--list",
    "-l",
    "input_list",
    required=False,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Import input list in plain text format",
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
    "no_count",
    is_flag=True,
    default=False,
    help="Skip k-mer counting with ntcard",
)
@click.option(
    "--leaf-grouping",
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
    "--ntt",
    "ntcard_threads",
    type=int,
    default=8,
    help="⚙️  Number of threads used by ntcard for k-mer counting (default: 8)",
)
def list_samples(
    input_dir,
    input_list,
    output_file,
    kmer_size,
    data_type,
    no_count,
    leaf_grouping,
    autorename,
    ntcard_threads,
):
    """Recursively list samples from a directory and output a JSONL file.

    By default, each file is treated as its own sample. Use --leaf-grouping
    to group files by leaf folder, where each leaf directory becomes one
    sample whose ID is the folder name.

    K-mer counting is enabled by default. Use --no-count to skip it. If the
    output file already exists and is incomplete, the run will resume from
    where it left off without recounting already-finished samples.
    """
    is_assembled = data_type.lower() in ("a", "assembled")
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
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except (NotADirectoryError, ValueError) as e:
        raise click.UsageError(str(e))
