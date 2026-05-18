"""Analyse a sample YAML file and produce a Bloom-filter span distribution."""

import logging
import math
import os

import click
import yaml

from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.core.kmer import KmerCounter
from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command(name="profile")
@click.option(
    "--input",
    "-i",
    "input",
    metavar="INPUT_FILE",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="📄  Sample YAML file (produced by `list`) containing k-mer counts.",
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
    required=False,
    help="🎯  Bloom filter false-positive rate (default: 0.25). "
    "A higher rate reduces disk footprint; the findere algorithm compensates at "
    "query time by using (k+z)-mers. Recommended: build with p=0.25, query with z=6.",
)
def profile(input, output_dir, n_groups, false_positive_rate):
    """Analyse a sample YAML file and output a Bloom-filter span profile.

    Reads the k-mer counts from INPUT_FILE (a YAML file produced by `list`), assigns each sample to a Bloom-filter span using the given
    false-positive rate, and writes a CSV summary together with a distribution
    plot to OUTPUT_DIR.

    \b
    Output files (written to OUTPUT_DIR):
      span_distribution.csv  — span id, Bloom filter size, and sample count
      span_distribution_analysis.png    — Span combination analysis plots

    \b
    Expected INPUT format:
      k: 25
      false_positive_rate: 0.25   # optional, overridden by --false-positive-rate
      samples:
        sample_name:
          kmer_count: 1234567
    """

    try:
        input = Toolbox.get_canonical_path(input)

        if not os.path.exists(input):
            raise click.ClickException(f"File not found: {input}")

        if input.endswith(".yaml") or input.endswith(".yml"):
            process_data(input, output_dir, false_positive_rate, n_groups)
        else:
            raise click.ClickException(
                f"Unsupported extension: must be '.yaml' or '.yml'."
            )
        logger.info("SUCCESS ('profile')")
    except Exception as e:
        Log.handle_exception(logger, e, "FAILED ('profile')")


def process_data(input, output_dir, false_positive_rate, n_groups):
    with open(input, "r") as f:
        data = yaml.safe_load(f)
    if not data:
        raise click.ClickException(f"Empty data: {input}")
    k = data.get("k")
    if not k:
        raise click.ClickException(f"Key 'k' not found or 0: {input}")
    samples = data.get("samples")
    if not samples:
        raise click.ClickException(f"Key 'samples' not found or empty: {input}")

    if not false_positive_rate:
        false_positive_rate = data.get("false_positive_rate", 0.25)

    sm = SpanManager(false_positive_rate)
    spans = {}

    for name, sample in samples.items():
        try:
            logger.debug(f"Process {name}...")
            kmer_count = sample.get("kmer_count", 0)
            if kmer_count:
                s, _ = sm.dispatch(kmer_count)
                spans[s] = spans.get(s, 0) + 1
            else:
                logger.warning(f"{name}: no field 'kmer_count'... skip")
        except Exception as e:
            Log.handle_exception(
                logger, e, f"Could not process sample '{name}'", level=logging.WARNING
            )

    os.makedirs(output_dir, exist_ok=True)
    original_distribution_file = os.path.join(output_dir, f"span_distribution.csv")
    with open(original_distribution_file, "w") as f:
        f.write("span,bf_size,sample_count\n")
        for span_id, sample_count in sorted(spans.items()):
            f.write(f"{span_id},{sm.get_bf_size(span_id)},{sample_count}\n")

    span_list = os.path.join(output_dir, f"span_list")
    with open(span_list, "w") as f:
        f.write(" ".join(str(s) for s in sorted(spans.keys())))

    try:
        import pykmhelpers.plots.span_analyzer

        sa = pykmhelpers.plots.span_analyzer.SpanAnalyzer(original_distribution_file)

        if n_groups == 0:
            n_groups = math.ceil(len(spans) / 3)
        elif n_groups == 1:
            n_groups = None

        sa.plot(n_groups=n_groups)
    except Exception as e:
        Log.handle_exception(logger, e, "Plot error", level=logging.ERROR)
