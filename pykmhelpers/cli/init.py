"""Recursively list samples from a directory and output a YAML file."""

import logging
import os

import click
import yaml

from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.core.kmer import KmerCounter
from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox

from ..plots.span_analyzer import SpanAnalyzer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command(name="init")
@click.option(
    "--input",
    "-i",
    "input",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Input list of sample files",
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory path",
)
@click.option(
    "--false-positive-rate",
    "--fp",
    type=float,
    required=False,
    help="False positive rate for Bloom filter (default: 0.25).\n\n==>IMPORTANT<== The findere algorithm optimizes queries by using (k+z)-mers to reduce the false positive rate at query time. This allows Bloom filters to be built with a higher false positive rate while still providing accurate results, which reduces disk footprint. Usually building your index with {k=25, p=0.25} and querying with z=6 provide a good balance.\n\n ",
)
def init_pipeline(input, output_dir, false_positive_rate):
    """"""
    input = Toolbox.get_canonical_path(input)

    if not os.path.exists(input):
        raise click.ClickException(f"File not found: {input}")

    if input.endswith(".yaml") or input.endswith(".yml"):
        process_data(input, output_dir, false_positive_rate)
    else:
        raise click.ClickException(f"Unsupported extension: must be '.yaml' or '.yml'.")


def process_data(input, output_dir, false_positive_rate):
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
        kmer_count = sample.get("kmer_count")
        if kmer_count:
            s, _ = sm.dispatch(kmer_count)
            spans[s] = spans.get(s, 0) + 1
        else:
            logger.warning(f"{name}: no field 'kmer_count'... skip")

    os.makedirs(output_dir, exist_ok=True)
    original_distribution_file = os.path.join(output_dir, f"span_distribution.csv")
    with open(original_distribution_file, "w") as f:
        f.write("span,bf_size,sample_count\n")
        for span_id, sample_count in sorted(spans.items()):
            f.write(f"{span_id},{sm.get_bf_size(span_id)},{sample_count}\n")

    sa = SpanAnalyzer(original_distribution_file)
    sa.plot()
