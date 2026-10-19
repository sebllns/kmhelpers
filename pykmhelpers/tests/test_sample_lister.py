"""Unit tests for SampleLister directory grouping, including --paired."""

import json
import tempfile
import unittest
from pathlib import Path

from pykmhelpers.core.constants import DEFAULT_PAIR_REGEX
from pykmhelpers.pipeline.sample_lister import SampleLister


class SampleListerPairingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "data"
        self.root.mkdir()

    def touch(self, *names, subdir=""):
        d = self.root / subdir
        d.mkdir(parents=True, exist_ok=True)
        for name in names:
            (d / name).write_text(">s\nACGT\n")

    def run_lister(self, **kwargs):
        out = Path(self._tmp.name) / "out.jsonl"
        SampleLister(
            output_file=str(out),
            input_dir=str(self.root),
            do_count=False,
            do_grouping=False,
            **kwargs,
        ).run()
        lines = out.read_text().splitlines()[1:]
        return {r["name"]: r["files"] for r in map(json.loads, lines)}

    def test_default_lists_each_file(self):
        self.touch("S1_R1.fq.gz", "S1_R2.fq.gz")
        with self.assertLogs("pykmhelpers.pipeline.sample_lister", "WARNING"):
            samples = self.run_lister()
        self.assertEqual(set(samples), {"S1_R1", "S1_R2"})

    def test_paired_default_regex(self):
        self.touch(
            "BSM41_METAB-16S_HGH7.UDI001-BID04-1_R1_clean.fastq.gz",
            "BSM41_METAB-16S_HGH7.UDI001-BID04-1_R2_clean.fastq.gz",
            "SRR123_1.fq.gz",
            "SRR123_2.fq.gz",
            "single.fa",
        )
        samples = self.run_lister(pair_regex=DEFAULT_PAIR_REGEX)
        self.assertEqual(
            samples,
            {
                "BSM41_METAB_16S_HGH7_UDI001_BID04_1_clean": [
                    "BSM41_METAB-16S_HGH7.UDI001-BID04-1_R1_clean.fastq.gz",
                    "BSM41_METAB-16S_HGH7.UDI001-BID04-1_R2_clean.fastq.gz",
                ],
                "SRR123": ["SRR123_1.fq.gz", "SRR123_2.fq.gz"],
                "single": ["single.fa"],
            },
        )

    def test_paired_only_within_directory(self):
        self.touch("S1_R1.fq", subdir="a")
        self.touch("S1_R2.fq", subdir="b")
        samples = self.run_lister(pair_regex=DEFAULT_PAIR_REGEX, autorename=True)
        self.assertEqual(samples, {"S1": ["a/S1_R1.fq"], "S1_1": ["b/S1_R2.fq"]})

    def test_paired_custom_regex(self):
        self.touch("x.fwd.fq", "x.rev.fq")
        samples = self.run_lister(pair_regex=r"\.(fwd|rev)$")
        self.assertEqual(samples, {"x": ["x.fwd.fq", "x.rev.fq"]})

    def test_paired_rejects_leaf_grouping_and_bad_regex(self):
        with self.assertRaises(ValueError):
            SampleLister("o.jsonl", pair_regex=DEFAULT_PAIR_REGEX, do_grouping=True)
        with self.assertRaises(ValueError):
            SampleLister("o.jsonl", pair_regex="(", do_grouping=False)


if __name__ == "__main__":
    unittest.main()
