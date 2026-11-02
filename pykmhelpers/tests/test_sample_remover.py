"""Unit tests for sample removal: column dropping in a matrix, and the
grouping of the samples by shard. kmindex is not needed."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from pykmhelpers.core.kmindex_layout import get_bytes_per_row, get_header_byte_size
from pykmhelpers.pipeline.sample_remover import SampleRemover, drop_columns, fof_names

HEADER = bytes(range(get_header_byte_size()))


def write_matrix(path, bits):
    """Write ``bits`` (rows x columns of 0/1) as a matrix, bit 0 first."""
    packed = np.packbits(np.asarray(bits, dtype=np.uint8), axis=1, bitorder="little")
    Path(path).write_bytes(HEADER + packed.tobytes())


def read_matrix(path, nb_bits):
    data = Path(path).read_bytes()
    assert data[: len(HEADER)] == HEADER
    row = get_bytes_per_row(nb_bits)
    body = np.frombuffer(data[len(HEADER) :], dtype=np.uint8).reshape(-1, row)
    return np.unpackbits(body, axis=1, bitorder="little")[:, :nb_bits]


class TestDropColumns(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.rng = np.random.default_rng(0)

    def check(self, nb_samples, bw, removed, rows=37, chunk_bytes=1 << 20):
        bits = self.rng.integers(0, 2, size=(rows, nb_samples * bw))
        src = os.path.join(self.tmp, "src.cmbf")
        dst = os.path.join(self.tmp, "dst.cmbf")
        write_matrix(src, bits)
        drop_columns(src, dst, nb_samples, bw, removed, chunk_bytes=chunk_bytes)
        kept = [s for s in range(nb_samples) if s not in removed]
        expected = [[r[s * bw + j] for s in kept for j in range(bw)] for r in bits]
        got = read_matrix(dst, len(kept) * bw)
        np.testing.assert_array_equal(
            got, np.asarray(expected, dtype=np.uint8).reshape(rows, len(kept) * bw)
        )
        self.assertEqual(
            os.path.getsize(dst), len(HEADER) + rows * get_bytes_per_row(len(kept) * bw)
        )

    def test_positions(self):
        for nb_samples in (5, 8, 9, 16, 21):
            for removed in ([0], [nb_samples - 1], [nb_samples // 2], [1, 2, 3]):
                with self.subTest(nb_samples=nb_samples, removed=removed):
                    self.check(nb_samples, 1, removed)

    def test_bw2(self):
        self.check(7, 2, [0, 4])
        self.check(12, 2, [11])

    def test_chunks_smaller_than_file(self):
        self.check(13, 1, [2, 7], rows=101, chunk_bytes=5)

    def test_no_row(self):
        self.check(6, 1, [3], rows=0)

    def test_truncated_matrix(self):
        src = os.path.join(self.tmp, "bad.cmbf")
        Path(src).write_bytes(HEADER + b"\x00" * 5)
        with self.assertRaises(ValueError):
            drop_columns(src, os.path.join(self.tmp, "out"), 9, 1, [0])


class RegistryBase(unittest.TestCase):
    """A registry of three shards, two partitions each, empty matrices."""

    SHARDS = {
        "idx_a": ["s0", "s1", "s2"],
        "idx_b": ["s3", "s4", "s1"],
        "idx_c": ["s5"],
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        index = {}
        for shard, samples in self.SHARDS.items():
            d = self.root / shard / "matrices"
            d.mkdir(parents=True)
            (self.root / shard / "kmtricks.fof").write_text(
                "".join(f"{s}: /data/{s}.fa\n" for s in samples)
            )
            for p in range(2):
                (d / f"matrix_{p}.cmbf").write_bytes(HEADER)
            index[shard] = {
                "nb_samples": len(samples),
                "samples": samples,
                "nb_partitions": 2,
                "bw": 1,
            }
        (self.root / "index.json").write_text(
            json.dumps({"path": str(self.root), "index": index})
        )
        self.remover = SampleRemover(str(self.root))


class TestResolve(RegistryBase):
    """Samples grouped by the shards holding them, whatever the list order."""

    def resolve(self, names, shards=None):
        removals, missing = self.remover.resolve(names, shards or list(self.SHARDS))
        return {r.shard: r for r in removals}, missing

    def test_unordered_and_shared(self):
        removals, missing = self.resolve(["s4", "s0", "unknown", "s1"])
        self.assertEqual(missing, {"unknown"})
        self.assertEqual(sorted(removals), ["idx_a", "idx_b"])
        self.assertEqual(removals["idx_a"].removed, ["s0", "s1"])
        self.assertEqual(removals["idx_a"].removed_idx, [0, 1])
        # in shard order, not list order
        self.assertEqual(removals["idx_b"].removed, ["s4", "s1"])
        self.assertEqual(removals["idx_b"].removed_idx, [1, 2])

    def test_selected_shards(self):
        removals, missing = self.resolve(["s1", "s3"], ["idx_b"])
        self.assertEqual(list(removals), ["idx_b"])
        self.assertEqual(missing, set())

    def test_problems(self):
        removals, _ = self.resolve(["s0", "s5"])
        self.assertEqual(self.remover.problems(removals["idx_a"]), [])
        self.assertIn("every sample", self.remover.problems(removals["idx_c"])[0])
        (self.root / "idx_a" / "compression.cfg").write_text("")
        self.assertIn("compressed", " ".join(self.remover.problems(removals["idx_a"])))

    def test_missing_matrix(self):
        removals, _ = self.resolve(["s0"])
        os.unlink(self.root / "idx_a" / "matrices" / "matrix_1.cmbf")
        self.assertIn("missing", " ".join(self.remover.problems(removals["idx_a"])))

    def test_fof_names(self):
        self.assertEqual(fof_names("a: x\n\n b : y ; z\n"), ["a", "b"])


class TestRecover(RegistryBase):
    """An interrupted removal is finished or undone; kmindex is mocked."""

    def interrupt(self, *parts):
        work = Path(self.remover.work_dir("idx_a"))
        work.mkdir(parents=True)
        for part in parts:
            if part == "previous":
                os.rename(self.root / "idx_a", work / "previous")
            elif part == "new":
                (work / "new").mkdir()
            else:
                (work / part).write_text("")
        return work

    def recover(self):
        with mock.patch.object(self.remover._kmindex, "register") as register:
            done = self.remover.recover()
        self.assertFalse((self.root / "work").exists())
        return done, register

    def test_nothing_to_recover(self):
        self.assertEqual(self.remover.recover(), [])

    def test_before_swap(self):
        self.interrupt("new")
        done, register = self.recover()
        self.assertEqual(done, ["idx_a: left as registered"])
        register.assert_not_called()

    def test_previous_restored(self):
        self.interrupt("previous", "new")
        done, register = self.recover()
        self.assertEqual(done, ["idx_a: previous version restored"])
        self.assertTrue((self.root / "idx_a" / "kmtricks.fof").is_file())
        register.assert_not_called()

    def test_new_published(self):
        work = self.interrupt("previous", "new", "checked")
        done, register = self.recover()
        self.assertEqual(done, ["idx_a: new version published"])
        register.assert_called_once_with(
            str(self.root), name="idx_a", index_path=str(work / "new"), mode="move"
        )
        self.assertNotIn("idx_a", json.loads((self.root / "index.json").read_text())["index"])


if __name__ == "__main__":
    unittest.main()
