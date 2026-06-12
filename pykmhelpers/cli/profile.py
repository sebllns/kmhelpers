"""Analyse a JSONL sample index and produce a Bloom-filter span distribution."""

import logging

import click

from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox
from pykmhelpers.pipeline.span_profiler import SpanProfiler

logger = logging.getLogger(__name__)


@click.command(name="profile")
@click.argument(
    "list_output",
    nargs=1,
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    metavar="OUTPUT_DIR",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory for the index profile and distribution files.",
)
@click.option(
    "--group",
    "-g",
    "n_groups",
    metavar="N_GROUPS",
    default=0,
    type=int,
    help="⚙   Partition index into N storage-balanced groups and overlay the result on the plot (default: 20). ",
)
@click.option(
    "--false-positive-rate",
    "--fp",
    type=float,
    default=0.25,
    help="🎯  Bloom filter false-positive rate (default: 0.25). "
    "A higher rate reduces disk footprint; the findere algorithm compensates at "
    "query time by using (k+z)-mers. Recommended: build with p=0.25, query with z=6.",
)
@click.option(
    "--base",
    "-b",
    type=click.FloatRange(min=1.0, min_open=True),
    default=2.0,
    help="⚙   Base for bucket boundaries (default: 2.0). "
    "Use values like 1.1 or 10 to widen or narrow bucket granularity.",
)
def profile(list_output, output_dir, n_groups, base, false_positive_rate):
    """Analyse a JSONL sample index and output a Bloom-filter profile.

    Reads the k-mer counts from LIST_OUTPUT (a JSONL file produced by `list`),
    assigns each sample to a Bloom-filter using the given false-positive
    rate, computes the natural distribution, then partitions index into
    N storage-balanced groups. Outputs a CSV, a profile YAML, and a distribution
    plot to OUTPUT_DIR. Samples without a `kmer_count` field are skipped.

    \b
    Output files (written to OUTPUT_DIR):
      span_distribution.csv  — natural distribution: span id, Bloom filter size, sample count
      profile.yaml           — natural distribution (baseline) and storage-balanced grouped profile(s)
      span_distribution_analysis.png  — distribution plot

    \b
    Expected LIST_OUTPUT format (JSONL):
      {"k": 25, "assembled": true, ...}
      {"name": "sample_name", "files": [...], "kmer_count": 1234567}
    """

    try:
        SpanProfiler(
            input_file=Toolbox.get_canonical_path(list_output),
            output_dir=output_dir,
            false_positive_rate=false_positive_rate,
            n_groups=n_groups,
            base=base,
        ).run()
        logger.info("SUCCESS ('profile')")
    except (ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    except Exception as e:
        Log.handle_exception(logger, e, "FAILED ('profile')")
