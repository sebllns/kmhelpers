"""Unit tests for query input handling: compressed files, stdin, batch mode
and the optional copy of the query into the output directory. kmindex is
mocked, no binary is needed."""

import bz2
import gzip
import io
import lzma
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
import zstandard

from pykmhelpers.core.constants import strip_data_ext
from pykmhelpers.core.utils import detect_compression, open_decompressed
from pykmhelpers.pipeline.query import KmindexQuery, QueryRunner, QueryRunnerConfig

FASTA = b">s1\nACGTACGT\n"
WRITERS = {
    ".gz": gzip.compress,
    ".bz2": bz2.compress,
    ".xz": lzma.compress,
    ".zst": zstandard.ZstdCompressor().compress,
}


class QueryInputsBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def write(self, name, data=FASTA):
        path = Path(self.tmp) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        ext = os.path.splitext(name)[1]
        path.write_bytes(WRITERS[ext](data) if ext in WRITERS else data)
        return str(path)

    def runner(self, **kwargs):
        return QueryRunner(
            QueryRunnerConfig(registry_path=self.tmp, output_dir=self.tmp, **kwargs)
        )


class TestHelpers(QueryInputsBase):
    def test_open_decompressed(self):
        for name in ("q.fa", "q.fa.gz", "q.fa.bz2", "q.fa.xz", "q.fa.zst"):
            with open_decompressed(self.write(name)) as f:
                self.assertEqual(f.read(), FASTA, name)

    def test_zip_rejected(self):
        with self.assertRaises(ValueError):
            open_decompressed(self.write("q.fa.zip"))

    def test_detect_compression(self):
        self.assertEqual(detect_compression(FASTA), "")
        for ext, compress in WRITERS.items():
            self.assertEqual(detect_compression(compress(FASTA)[:6]), ext)

    def test_strip_data_ext(self):
        self.assertEqual(strip_data_ext("q.fa.gz"), "q")
        self.assertEqual(strip_data_ext("q.fastq.bz2"), "q")


class TestResolveFiles(QueryInputsBase):
    def test_directory_scan(self):
        for name in ("a.fa", "b.fa.gz", "c.fq.bz2", "d.fa.zst", "notes.txt"):
            self.write(f"dir/{name}")
        resolved, temp_files = self.runner()._resolve_files([f"{self.tmp}/dir"])
        self.addCleanup(QueryRunner._remove_temp, temp_files)

        names = sorted(os.path.basename(p) for p in resolved)
        self.assertEqual(names, ["a.fa", "b.fa.gz", "c.fq", "d.fa"])
        # bz2 and zst are decompressed to temp files, gz passes through
        for name in ("c.fq", "d.fa"):
            path = next(p for p in resolved if p.endswith(name))
            self.assertEqual(Path(path).read_bytes(), FASTA)
        self.assertEqual(len(temp_files), 2)

    def test_stdin_compressed(self):
        stdin = mock.Mock(buffer=io.BytesIO(gzip.compress(FASTA)))
        with mock.patch.object(sys, "stdin", stdin):
            resolved, temp_files = self.runner()._resolve_files(["-"])
        self.addCleanup(QueryRunner._remove_temp, temp_files)
        self.assertTrue(resolved[0].endswith(".fa.gz"))

    def test_temp_files_removed(self):
        self.write("d.fa.xz")
        resolved, temp_files = self.runner()._resolve_files([f"{self.tmp}/d.fa.xz"])
        QueryRunner._remove_temp(temp_files)
        self.assertFalse(os.path.exists(resolved[0]))
        self.assertFalse(os.path.exists(temp_files[0]))


class TestBatch(QueryInputsBase):
    def test_mixed_compressions(self):
        files = [
            self.write("a.fa", b">a\nAC"),
            self.write("b.fa.gz", b">b\nGT\n"),
            self.write("c.fa.bz2", b">c\nTT\n"),
        ]
        captured = {}

        def fake_run(qfile, total, idx):
            captured["data"] = Path(qfile).read_bytes()
            return ["ok"]

        runner = self.runner(batch=True)
        with mock.patch.object(runner, "_run_single_safe", side_effect=fake_run):
            runner.run(files)
        self.assertEqual(captured["data"], b">a\nAC\n>b\nGT\n>c\nTT\n")


class TestKeepQuery(QueryInputsBase):
    def execute(self, keep_query):
        query = self.write("q.fa.gz")
        out = os.path.join(self.tmp, f"out_{keep_query}")
        def fake_query(**kwargs):
            os.makedirs(kwargs["output_dir"])
            return {}

        with mock.patch(
            "pykmhelpers.pipeline.query.KmindexWrapper.query", side_effect=fake_query
        ) as wrapped:
            KmindexQuery(path=query).execute(
                registry_path=self.tmp, output_dir=out, keep_query=keep_query
            )
        self.assertEqual(wrapped.call_args.kwargs["query_file"], query)
        info = yaml.safe_load(Path(out, "info.yaml").read_text())
        self.assertEqual(info["query_file"], os.path.abspath(query))
        return os.listdir(out)

    def test_no_copy_by_default(self):
        self.assertNotIn("q.fa.gz", self.execute(keep_query=False))

    def test_copy_on_request(self):
        self.assertIn("q.fa.gz", self.execute(keep_query=True))


if __name__ == "__main__":
    unittest.main()
