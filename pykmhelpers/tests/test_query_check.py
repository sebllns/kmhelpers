"""Unit tests for the sample side of the query check (no kmindex needed)."""

import gzip
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import zstandard

from pykmhelpers.core.index import IndexCompressionState
from pykmhelpers.pipeline.query_check import (
    ShardQueryCheck,
    expected_fpr,
    first_sample_file,
    negative_scores,
    query_check,
    random_dna,
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

    def test_summary_with_negatives(self):
        check = ShardQueryCheck(
            sample="S1", scores=[1.0], neg_scores={"S1": 0.01, "S2": 0.03}, expected=0.002
        )
        self.assertEqual(
            check.summary(),
            "S1 mean 1.000, min 1.000, 1/1 perfect; negatives mean 0.0200, "
            "max 0.0300 (S2), expected 0.0020",
        )


class TestGap(unittest.TestCase):
    def test_sound_shard(self):
        check = ShardQueryCheck(sample="S1", scores=[1.0, 0.8], neg_scores={"S1": 0.0, "S2": 0.1})
        self.assertAlmostEqual(check.gap, 0.85)
        self.assertFalse(check.broken())

    def test_broken_shards(self):
        # empty filters: nothing hits; saturated filters: everything hits
        empty = ShardQueryCheck(sample="S1", scores=[0.0, 0.0], neg_scores={"S1": 0.0})
        full = ShardQueryCheck(sample="S1", scores=[1.0], neg_scores={"S1": 1.0})
        self.assertTrue(empty.broken())
        self.assertTrue(full.broken())
        self.assertFalse(full.broken(min_gap=0.0))

    def test_no_gate_without_scores(self):
        self.assertIsNone(ShardQueryCheck(skipped="x").gap)
        self.assertFalse(ShardQueryCheck(skipped="x").broken())
        self.assertFalse(ShardQueryCheck(sample="S1", scores=[1.0]).broken())

    def test_suspect(self):
        check = ShardQueryCheck(sample="S1", scores=[1.0], neg_scores={"S1": 0.05})
        self.assertFalse(check.suspect())
        check.expected = 0.001
        self.assertTrue(check.suspect())
        check.expected = 0.01
        self.assertFalse(check.suspect())

    def test_expected_fpr_with_findere(self):
        self.assertIsNone(expected_fpr({}, 3))
        self.assertAlmostEqual(expected_fpr({"a": 0.5, "b": 0.1}, 0), 0.3)
        self.assertAlmostEqual(expected_fpr({"a": 0.5}, 2), 0.125)

    def test_negative_scores(self):
        queries = {".neg__0": {"S1": 0.2}, ".neg__1": {"S1": 0.0, "S2": 0.4}}
        self.assertEqual(
            negative_scores(queries, ["S1", "S2", "S3"], 2), {"S1": 0.1, "S2": 0.2, "S3": 0.0}
        )
        self.assertEqual(negative_scores({}, ["S1"], 0), {})

    def test_random_dna(self):
        seqs = random_dna(50, 3, random.Random(0))
        self.assertEqual([len(s) for s in seqs], [50, 50, 50])
        self.assertTrue(all(set(s) <= set("ACGT") for s in seqs))


class FakeQuery:
    """KmindexQuery reading the FASTA it is given: positives hit their own
    sample, negatives hit S2 of every shard at 0.25."""

    def __init__(self, path):
        self.path = path

    def execute(self, index_ids, **kwargs):
        names = [line[1:].strip() for line in open(self.path) if line.startswith(">")]
        items = {}
        for shard in index_ids:
            items[shard] = {
                n: ({"S2": 0.25} if n.startswith(".neg") else {"S1": 1.0})
                for n in names
                if n.startswith(".neg") or n.startswith(f"{shard}__")
            }
        return [SimpleNamespace(items=items)]


class TestQueryCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_qc_"))
        rng = random.Random(1)
        sample = self.tmp / "s1.fa"
        sample.write_text(">s\n" + "".join(rng.choice("ACGT") for _ in range(500)) + "\n")
        fof = self.tmp / "kmtricks.fof"
        fof.write_text(f"S1 : {sample}\nS2 : {sample}\n")
        index = SimpleNamespace(
            fof_path=str(fof),
            kmer_size=25,
            compress_state=IndexCompressionState.UNCOMPRESSED,
            samples=["S1", "S2"],
        )
        self.registry = SimpleNamespace(root_path=str(self.tmp), get_index=lambda name: index)
        stats = self.tmp / "logs" / "a" / "stats.yaml"
        stats.parent.mkdir(parents=True)
        stats.write_text("fpr_samples:\n  S1: 0.001\n  S2: 0.003\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_positives_negatives_and_expected(self):
        with mock.patch("pykmhelpers.pipeline.query_check.KmindexQuery", FakeQuery):
            checks = query_check(self.registry, ["a", "b"], 0, 5, random.Random(0), 4, 100)
        a, b = checks["a"], checks["b"]
        self.assertEqual(a.scores, [1.0] * 5)
        self.assertEqual(a.neg_scores, {"S1": 0.0, "S2": 0.25})
        self.assertAlmostEqual(a.expected, 0.002)
        # no stats recorded for b
        self.assertIsNone(b.expected)
        self.assertFalse(a.broken())
        # 0.125 on the negatives, 0.002 expected
        self.assertTrue(a.suspect())
        self.assertFalse(b.suspect())


if __name__ == "__main__":
    unittest.main()
