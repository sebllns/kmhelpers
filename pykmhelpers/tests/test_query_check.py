"""Unit tests for the sample side of the query check (no kmindex needed)."""

import gzip
import random
import shutil
import tempfile
import unittest
from pathlib import Path

import zstandard

from pykmhelpers.pipeline.query_check import (
    ShardQueryCheck,
    first_sample_file,
    random_windows,
)


class TestRandomWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_qc_"))
        rng = random.Random(1)
        self.seq = "".join(rng.choice("ACGT") for _ in range(500))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def windows(self, path, length=37, count=10):
        return random_windows(str(path), length, count, random.Random(0))

    def test_fasta_windows_are_substrings(self):
        path = self.tmp / "s.fa"
        path.write_text(f">s\n{self.seq[:250]}\n{self.seq[250:]}\n")
        windows = self.windows(path)
        self.assertEqual(len(windows), 10)
        for w in windows:
            self.assertEqual(len(w), 37)
            self.assertIn(w, self.seq)

    def test_fastq_gz(self):
        path = self.tmp / "s.fq.gz"
        with gzip.open(path, "wt") as f:
            for i in range(0, 500, 100):
                read = self.seq[i : i + 100]
                f.write(f"@r{i}\n{read}\n+\n{'I' * len(read)}\n")
        windows = self.windows(path)
        self.assertEqual(len(windows), 10)
        reads = [self.seq[i : i + 100] for i in range(0, 500, 100)]
        for w in windows:
            self.assertTrue(any(w in r for r in reads), w)

    def test_fasta_zst(self):
        path = self.tmp / "s.unitigs.fa.zst"
        path.write_bytes(zstandard.ZstdCompressor().compress(f">s\n{self.seq}\n".encode()))
        windows = self.windows(path)
        self.assertEqual(len(windows), 10)
        for w in windows:
            self.assertIn(w, self.seq)

    def test_skips_n_and_short_records(self):
        path = self.tmp / "s.fa"
        # one 10-base ACGT run between Ns (1 window), a 12-base record (3 windows)
        path.write_text(">a\nNNACGTACGTACNN\n>b\nacgtacgtacgt\n")
        windows = self.windows(path, length=10)
        self.assertEqual(len(windows), 4)
        self.assertIn("ACGTACGTAC", windows)
        for w in windows:
            self.assertNotIn("N", w)
        self.assertEqual(self.windows(path, length=13), [])

    def test_fewer_when_not_enough(self):
        path = self.tmp / "s.fa"
        path.write_text(">a\nACGTACGTACGT\n")
        self.assertEqual(len(self.windows(path, length=10, count=10)), 3)


class TestFirstSampleFile(unittest.TestCase):
    def test_first_file_without_abundance(self):
        with tempfile.NamedTemporaryFile("w", suffix=".fof", delete=False) as f:
            f.write("\nS1 : /d/a.fq.gz ; /d/b.fq.gz ! 2\nS2 : /d/c.fa\n")
        try:
            self.assertEqual(first_sample_file(f.name), ("S1", "/d/a.fq.gz"))
        finally:
            Path(f.name).unlink()


class TestSummary(unittest.TestCase):
    def test_summary(self):
        check = ShardQueryCheck(sample="S1", scores=[1.0, 0.5])
        self.assertEqual(check.summary(), "S1 mean 0.750, min 0.500, 1/2 perfect")
        self.assertEqual(ShardQueryCheck(skipped="x").summary(), "skipped (x)")
        self.assertEqual(ShardQueryCheck(sample="S1", scores=[]).summary(), "S1: no score")


if __name__ == "__main__":
    unittest.main()
