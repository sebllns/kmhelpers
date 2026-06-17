"""Analyse a JSONL sample index and produce a Bloom-filter span distribution."""

import json
import logging
import math
import os

import yaml

from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.core.log import Log

logger = logging.getLogger(__name__)


class SpanProfiler:
    """Read a JSONL sample index and write a Bloom-filter span distribution.

    Reads the header line for ``k`` (and optionally ``false_positive_rate``),
    then iterates over sample entries to assign each to a Bloom-filter span
    based on its k-mer count.  Outputs a ``baseline.csv`` and, when
    the plot module is available, a ``profile.yaml`` alongside the
    ``groups.png`` analysis plot.

    Args:
        input_file:          Path to the JSONL sample index (produced by ``list``).
        output_dir:          Directory where output files are written.
        false_positive_rate: Bloom filter false-positive rate (default 0.25).
        n_groups:            Number of storage-balanced span groups (0 = auto).
    """

    def __init__(
        self,
        input_file: str,
        output_dir: str,
        false_positive_rate: float = 0.25,
        n_groups: int = 20,
        base: float = 2.0,
    ):
        self.input_file = input_file
        self.output_dir = output_dir
        self.false_positive_rate = false_positive_rate
        self.n_groups = n_groups
        self.base = base

    def run(self) -> None:
        with open(self.input_file) as f:
            try:
                header = json.loads(f.readline())
            except (json.JSONDecodeError, ValueError):
                raise ValueError(f"Could not parse header line: {self.input_file}")

            k = header.get("k")
            if not k:
                raise ValueError(f"Key 'k' not found or 0 in header: {self.input_file}")

            sm = SpanManager(p=self.false_positive_rate, b=self.base)
            spans: dict[int, int] = {}
            biggest_sample: tuple[str, int] = ("", 0)
            sample_count = 0

            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse entry: {line}")
                    continue

                name = entry.get("name")
                if not name:
                    continue

                sample_count += 1
                try:
                    logger.debug(f"Process {name}...")
                    kmer_count = entry.get("kmer_count", 0)
                    if kmer_count:
                        s = sm.dispatch(kmer_count)
                        spans[s] = spans.get(s, 0) + 1
                        if kmer_count > biggest_sample[1]:
                            biggest_sample = (name, kmer_count)
                    else:
                        logger.warning(f"{name}: no field 'kmer_count'... skip")
                except Exception as e:
                    Log.handle_exception(
                        logger,
                        e,
                        f"Could not process sample '{name}'",
                        level=logging.WARNING,
                    )

        if not spans:
            raise ValueError(
                f"No samples with k-mer counts found in: {self.input_file}"
            )

        os.makedirs(self.output_dir, exist_ok=True)
        distribution_file = os.path.join(self.output_dir, "baseline.csv")
        with open(distribution_file, "w") as f:
            f.write("span,bf_size,sample_count\n")
            for span_id, count in sorted(spans.items()):
                f.write(f"{span_id},{sm.get_bf_size(span_id)},{count}\n")

        baseline = sorted(spans.keys())

        try:
            import pykmhelpers.pipeline.span_analyzer

            sa = pykmhelpers.pipeline.span_analyzer.SpanAnalyzer(distribution_file)

            n_groups = self.n_groups

            sa.plot(n_groups=n_groups)

            with open(os.path.join(self.output_dir, "profile.yaml"), "w") as f:
                yaml.dump(
                    {
                        "false_positive_rate": self.false_positive_rate,
                        "span_base": self.base,
                        "sample_count": sample_count,
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
