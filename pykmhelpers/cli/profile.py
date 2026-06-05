"""Analyse a JSONL sample index and produce a Bloom-filter span distribution."""

import logging

import click

from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox
from pykmhelpers.pipeline.span_profiler import SpanProfiler

logger = logging.getLogger(__name__)


@click.command(name="profile")
@click.option(
    "--input",
    "-i",
    "input",
    metavar="INPUT_FILE",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="📄  JSONL sample index (produced by `list`) containing k-mer counts.",
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    metavar="OUTPUT_DIR",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory for the span distribution CSV and analysis plot.",
)
@click.option(
    "--group",
    "-g",
    "n_groups",
    metavar="N_GROUPS",
    default=0,
    type=int,
    help="⚙   Partition spans into N storage-balanced groups and overlay the result on the plot (default: 0). "
    "Pass 0 to let the analyser choose the optimal number of groups automatically. ",
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
def profile(input, output_dir, n_groups, false_positive_rate):
    """Analyse a JSONL sample index and output a Bloom-filter span profile.

    Reads the k-mer counts from INPUT_FILE (a JSONL file produced by `list`),
    assigns each sample to a Bloom-filter span using the given false-positive
    rate, and writes a CSV summary together with a distribution plot to
    OUTPUT_DIR.

    \b
    Output files (written to OUTPUT_DIR):
      span_distribution.csv           — span id, Bloom filter size, sample count
      span_distribution_analysis.png  — Span combination analysis plots

    \b
    Expected INPUT format (JSONL):
      {"k": 25, "assembled": true, ...}
      {"name": "sample_name", "files": [...], "kmer_count": 1234567}
    """
    try:
        SpanProfiler(
            input_file=Toolbox.get_canonical_path(input),
            output_dir=output_dir,
            false_positive_rate=false_positive_rate,
            n_groups=n_groups,
        ).run()
        logger.info("SUCCESS ('profile')")
    except (ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    except Exception as e:
        Log.handle_exception(logger, e, "FAILED ('profile')")
