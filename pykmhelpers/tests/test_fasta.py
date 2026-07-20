"""Unit tests for pykmhelpers.core.fasta (non-validation features).

Covers the ``Fasta`` container, the ``open_sequence_file`` helper and the
``FASTAReader`` accessors. Validation is tested separately in
``test_fasta_validation.py``.
"""

import gzip
import os
import tempfile
import unittest

from pykmhelpers.core.fasta import Fasta, FASTAReader, open_sequence_file


class TestFasta(unittest.TestCase):
    """Tests for the in-memory Fasta container."""

    def test_empty_by_default(self):
        fasta = Fasta()
        self.assertEqual(fasta.n_sequences, 0)
        self.assertEqual(fasta.total_nucleotides(), 0)

    def test_fill_random_count_and_headers(self):
        fasta = Fasta()
        fasta.fill_random(num_sequences=5, average_size=100, min_size=50, header="s_")
        self.assertEqual(fasta.n_sequences, 5)
        headers = [s.header for s in fasta]
        # Zero-padded indices, consistent width.
        self.assertEqual(headers[0], "s_0")
        self.assertTrue(all(h.startswith("s_") for h in headers))

    def test_fill_random_respects_size_bounds(self):
        fasta = Fasta()
        fasta.fill_random(num_sequences=10, average_size=80, min_size=40)
        for seq in fasta:
            self.assertGreaterEqual(len(seq), 40)
            self.assertLessEqual(len(seq), 80)

    def test_total_nucleotides_matches_len(self):
        fasta = Fasta()
        fasta.fill_random(num_sequences=4, average_size=30, min_size=30)
        self.assertEqual(fasta.total_nucleotides(), len(fasta))
        self.assertEqual(len(fasta), sum(len(s) for s in fasta))

    def test_to_fasta_format(self):
        fasta = Fasta()
        fasta.fill_random(num_sequences=2, average_size=10, min_size=10, header="x")
        text = fasta.to_fasta()
        self.assertEqual(str(fasta), text)
        self.assertEqual(text.count(">"), 2)
        self.assertTrue(text.startswith(">x0"))

    def test_create_random_test_dataset_writes_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "dataset")
            Fasta.create_random_test_dataset(out, n_samples=3, average_size=50, min_size=50)
            files = [f for f in os.listdir(out) if f.endswith(".fasta")]
            self.assertEqual(len(files), 3)
            # Each written file is a valid single-record FASTA.
            for name in files:
                with open(os.path.join(out, name)) as f:
                    content = f.read()
                self.assertTrue(content.startswith(">"))


class TestOpenSequenceFile(unittest.TestCase):
    """Tests for the plain/gzip/zstandard open helper."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.payload = ">s\nACGTACGT\n"

    def tearDown(self):
        self.tmp.cleanup()

    def test_open_plain(self):
        path = os.path.join(self.dir, "s.fasta")
        with open(path, "w") as f:
            f.write(self.payload)
        with open_sequence_file(path) as fh:
            self.assertEqual(fh.read(), self.payload)

    def test_open_gzip(self):
        path = os.path.join(self.dir, "s.fasta.gz")
        with gzip.open(path, "wt") as f:
            f.write(self.payload)
        with open_sequence_file(path) as fh:
            self.assertEqual(fh.read(), self.payload)

    def test_open_zstandard(self):
        try:
            import zstandard
        except ImportError:
            self.skipTest("zstandard not installed")
        path = os.path.join(self.dir, "s.fasta.zst")
        cctx = zstandard.ZstdCompressor()
        with open(path, "wb") as f:
            f.write(cctx.compress(self.payload.encode()))
        with open_sequence_file(path) as fh:
            self.assertEqual(fh.read(), self.payload)


class TestFASTAReader(unittest.TestCase):
    """Tests for FASTAReader format checks and accessors."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.content = (
            ">contig_1 first contig\n"
            "ACGTACGTAC\n"
            "GTACGTACGT\n"
            ">contig_2\n"
            "TTTTGGGGCC\n"
        )
        self.path = os.path.join(self.dir, "seqs.fasta.gz")
        with gzip.open(self.path, "wt") as f:
            f.write(self.content)

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_compression(self):
        # A plain (uncompressed) extension is rejected by FASTAReader.
        with self.assertRaises(ValueError):
            FASTAReader(os.path.join(self.dir, "plain.fasta"))

    def test_rejects_unknown_sequence_ext(self):
        with self.assertRaises(ValueError):
            FASTAReader(os.path.join(self.dir, "data.txt.gz"))

    def test_fetch_first_n(self):
        reader = FASTAReader(self.path)
        seq = reader.fetch_first_n(5)
        self.assertEqual(seq.content, "ACGTA")

    def test_fetch_first_n_with_offset(self):
        reader = FASTAReader(self.path)
        seq = reader.fetch_first_n(4, offset=2)
        self.assertEqual(seq.content, "GTAC")

    def test_fetch_sequence_full(self):
        reader = FASTAReader(self.path)
        self.assertEqual(reader.fetch_sequence("contig_1"), "ACGTACGTACGTACGTACGT")

    def test_fetch_sequence_range(self):
        reader = FASTAReader(self.path)
        self.assertEqual(reader.fetch_sequence("contig_1", start=2, end=6), "GTAC")

    def test_fetch_sequence_missing_contig(self):
        reader = FASTAReader(self.path)
        with self.assertRaises(ValueError):
            reader.fetch_sequence("does_not_exist")

    def test_iter_sequences(self):
        reader = FASTAReader(self.path)
        records = list(reader.iter_sequences())
        self.assertEqual([name for name, _ in records], ["contig_1", "contig_2"])
        self.assertEqual(records[1][1], "TTTTGGGGCC")

    def test_iter_with_header(self):
        reader = FASTAReader(self.path)
        headers = [h for h, _ in reader.iter_with_header()]
        self.assertEqual(headers[0], "contig_1 first contig")


if __name__ == "__main__":
    unittest.main()