"""Unit tests for SampleLister directory grouping, including --paired."""

import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pykmhelpers.core.constants import DEFAULT_PAIR_REGEX
from pykmhelpers.pipeline import sample_lister
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
            samples = self.run_lister(is_assembled=False)
        self.assertEqual(set(samples), {"S1_R1", "S1_R2"})

    def test_no_pair_warning_for_assembled(self):
        self.touch("genome_1.fa", "genome_2.fa")
        with mock.patch.object(sample_lister.logger, "warning") as warning:
            samples = self.run_lister()
        warning.assert_not_called()
        self.assertEqual(set(samples), {"genome_1", "genome_2"})

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


@unittest.skipUnless(shutil.which("ntcard"), "ntcard not on PATH")
class SampleListerCountTest(unittest.TestCase):
    """One ntcard run gives kmer_count and kmer_total (occurrences)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "data"
        self.root.mkdir()
        rng = random.Random(0)
        seq = "".join(rng.choice("ACGT") for _ in range(50000))
        # the same sequence 4 times: every k-mer is solid and seen 4 times
        # (ntcard estimates from a sketch: too small an input reads as empty)
        (self.root / "S1.fa").write_text("".join(f">r{n}\n{seq}\n" for n in range(4)))

    def count(self, **kwargs):
        out = Path(self._tmp.name) / "out.jsonl"
        SampleLister(
            output_file=str(out),
            input_dir=str(self.root),
            do_grouping=False,
            kmer_size=25,
            **kwargs,
        ).run()
        return json.loads(out.read_text().splitlines()[1])

    def test_raw_reads_record_occurrences(self):
        entry = self.count(is_assembled=False)
        self.assertGreater(entry["kmer_count"], 0)
        self.assertGreater(entry["kmer_total"], entry["kmer_count"])

    def test_assembled_records_occurrences_too(self):
        entry = self.count()
        self.assertGreater(entry["kmer_total"], entry["kmer_count"])
