"""Analyse a sample YAML file and produce a Bloom-filter span profile and distribution."""

import logging
import math
import os

import click
import yaml

from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.core.byte import ByteCounter
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

    A *span* is an integer s = floor(log2(n)), where n is the number of
    distinct $k$-mers in a sample. It identifies the Bloom-filter size class
    required to index that sample at the target false-positive rate: all
    samples in span s have between 2^s and 2^(s+1)-1 distinct $k$-mers and
    are stored in a Bloom filter of the same size. A *span profile* is the
    distribution of samples across spans, together with candidate groupings
    of those spans into sub-indices and a recommended grouping that minimises
    the number of sub-indices while balancing storage cost. Fewer spans means
    fewer index files opened at query time, which can significantly improve
    query performance on I/O-bound storage.

    Reads the $k$-mer counts from INPUT_FILE (a YAML file produced by `list`),
    assigns each sample to a span using the given false-positive rate, and
    writes a CSV summary, a distribution plot, and a YAML profile to OUTPUT_DIR.

    \b
    Output files (written to OUTPUT_DIR):
      span_distribution.csv         — span id, Bloom filter size, and sample count
      span_distribution_analysis.png — span combination analysis plots
      profile.yaml                  — summary: k, false-positive rate, sample count,
                                      biggest sample, max k-mer count, and the
                                      recommended profile with all alternatives

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
    biggest_sample = ("", 0)

    for name, sample in samples.items():
        try:
            logger.debug(f"Process {name}...")
            kmer_count = sample.get("kmer_count", 0)
            if kmer_count:
                s = sm.dispatch(kmer_count)
                spans[s] = spans.get(s, 0) + 1
                if kmer_count > biggest_sample[1]:
                    biggest_sample = (name, kmer_count)

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

    baseline = sorted(spans.keys())

    try:
        import pykmhelpers.plots.span_analyzer

        sa = pykmhelpers.plots.span_analyzer.SpanAnalyzer(original_distribution_file)

        if n_groups == 0:
            n_groups = math.ceil(len(spans) / 3)
        elif n_groups == 1:
            n_groups = None

        sa.plot(n_groups=n_groups)

        with open(os.path.join(output_dir, f"profile.yaml"), "w") as f:
            yaml.dump(
                {
                    "k": k,
                    "false_positive_rate": false_positive_rate,
                    "sample_count": len(samples),
                    "biggest_sample": str(biggest_sample),
                    "max_kmer_count": sm.max_kmer_count(baseline[-1]),
                    "default_profile": sa.default_profile or "baseline",
                    "profiles": sa.serialize_profiles(),
                },
                f,
                default_flow_style=False,
                sort_keys=False,
            )

    except Exception as e:
        Log.handle_exception(logger, e, "Plot error", level=logging.ERROR)
