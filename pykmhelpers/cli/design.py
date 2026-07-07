"""Scan a directory, profile k-mer spans, and compose index definition files."""

import datetime
import logging
import os

import click

from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox
from pykmhelpers.pipeline.composer import IndexComposer
from pykmhelpers.pipeline.sample_lister import SampleLister
from pykmhelpers.pipeline.span_profiler import SpanProfiler

logger = logging.getLogger(__name__)


@click.command(name="design")
@click.argument(
    "input",
    nargs=1,
    required=True,
    type=click.Path(exists=True),
)
@click.option(
    "--output-dir",
    "-o",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory.",
)
@click.option(
    "--name",
    "-n",
    required=True,
    help="🏷️   Name of created index.",
)
@click.option(
    "--session-id",
    "-S",
    required=False,
    default=lambda: datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
    show_default="current timestamp",
    help="🏷️   Session tag appended to index names.",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    show_default=True,
    help="🧬  K-mer size used for counting.",
)
@click.option(
    "--data-type",
    "-dt",
    "data_type",
    type=click.Choice(["a", "assembled", "u", "unassembled"], case_sensitive=False),
    default="a",
    show_default=True,
    help="🧬  Data type: a/assembled (default) or u/unassembled (raw reads).",
)
@click.option(
    "--group",
    "-g",
    "n_groups",
    metavar="N_GROUPS",
    default=20,
    type=int,
    show_default=True,
    help="⚙   Partition index into N storage-balanced groups and overlay the result on the plot.",
)
@click.option(
    "--base",
    "-b",
    type=click.FloatRange(min=1.0, min_open=True),
    default=1.1,
    show_default=True,
    help="⚙   Base for bucket boundaries. "
    "Use values like 1.1 or 2 to widen or narrow bucket granularity.",
)
@click.option(
    "--no-count",
    "-nc",
    "no_count",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩   Skip k-mer counting with ntcard.",
)
@click.option(
    "--leaf-grouping",
    "-lg",
    "leaf_grouping",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Group files by leaf folder; each leaf directory becomes one sample.",
)
@click.option(
    "--autorename",
    "-r",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Rename duplicate sample IDs by appending a numeric suffix instead of skipping.",
)
@click.option(
    "--ntcard-threads",
    "-ntt",
    "ntcard_threads",
    type=int,
    default=8,
    show_default=True,
    help="⚙️  Number of threads used by ntcard for k-mer counting.",
)
@click.option(
    "--false-positive-rate",
    "-fp",
    type=float,
    default=0.25,
    show_default=True,
    help="🎯  Bloom filter false-positive rate p. "
    "A higher rate reduces disk footprint; the findere algorithm compensates at "
    "query time by using (k+z)-mers, reducing the effective FP rate to p^z. "
    "See NOTE and RECOMMENDED above.",
)
@click.option(
    "--partition-count",
    "-p",
    type=int,
    default=0,
    show_default=True,
    help="💾  Desired number of partitions per index, 0 for automatic count.",
)
def lpc(
    input,
    output_dir,
    name,
    session_id,
    kmer_size,
    data_type,
    no_count,
    leaf_grouping,
    autorename,
    ntcard_threads,
    n_groups,
    false_positive_rate,
    base,
    partition_count,
):
    """Scan a directory, profile k-mer spans, and compose index definition files.

    Runs the pipeline [list → profile → compose] in a single command.
    INPUT can be a directory (scanned recursively) or a sample list file.

    \b
    Input:  directory to scan, or a plain-text / YAML sample list
    Output: OUTPUT_DIR/list/ (JSONL), OUTPUT_DIR/profile/ (profile.yaml, groups.png),
            OUTPUT_DIR/compose/ (index definitions)

    \b
    Steps:
      1. list    - scan INPUT, count k-mers, write JSONL output file to OUTPUT_DIR/list/
      2. profile - compute Bloom-filter span distribution, write profile.yaml to OUTPUT_DIR/profile/
      3. compose - build index definition files to OUTPUT_DIR/compose/

    \b
    ► NOTE: At query time, the effective FP rate is reduced to p^z, where p is
      the build-time rate (--fp) and z is a query-time parameter.
    ► RECOMMENDED: build with p=0.25, query with z=6 (effective FP rate: 0.25^6 ≈ 0.024%).
    """

    is_assembled = data_type.lower() in ("a", "assembled")
    input_dir = input if os.path.isdir(input) else None
    input_list = input if os.path.isfile(input) else None

    list_dir = os.path.join(output_dir, "list")
    profile_dir = os.path.join(output_dir, "profile")
    compose_dir = os.path.join(output_dir, "compose")
    for d in (list_dir, profile_dir, compose_dir):
        os.makedirs(d, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = os.path.join(list_dir, f"{name}_samples_{timestamp}.jsonl")
    profiles_file = os.path.join(profile_dir, "profile.yaml")
    auto_layout = os.path.join(compose_dir, f"{name}_layout.yaml")

    try:
        SampleLister(
            output_file=jsonl_path,
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
    except (FileNotFoundError, NotADirectoryError, ValueError) as e:
        raise click.ClickException(f"FAILED ('list'): {e}")
    except Exception as e:
        Log.handle_exception(logger, e, "FAILED ('list')")
        raise

    layout_file = None
    if os.path.isfile(auto_layout):
        layout_file = auto_layout
        profiles_file = None
        logger.info("Found existing layout file, updating existing index")
    else:
        try:
            SpanProfiler(
                input_file=Toolbox.get_canonical_path(jsonl_path),
                output_dir=profile_dir,
                false_positive_rate=false_positive_rate,
                n_groups=n_groups,
                base=base,
            ).run()
            logger.info("SUCCESS ('profile')")
        except (FileNotFoundError, ValueError) as e:
            raise click.ClickException(f"FAILED ('profile'): {e}")
        except Exception as e:
            Log.handle_exception(logger, e, "FAILED ('profile')")
            raise

    try:
        IndexComposer(
            profiles_file=profiles_file,
            layout_file=layout_file,
            selected_profile=None,
            name=name,
            partition_count=partition_count,
            bf_max_size=ByteCounter.from_str("512GB"),
            partition_min_size=ByteCounter.from_str("4GB"),
            no_merge=False,
            exact_partition_count=False,
            partition_count_limit=256,
        ).run(
            input_file=jsonl_path,
            output_dir=compose_dir,
            run_id=session_id,
        )
        logger.info("SUCCESS ('compose')")
    except Exception as e:
        Log.handle_exception(logger, e, "FAILED ('compose')")
        raise click.ClickException("FAILED ('compose')")
        raise
