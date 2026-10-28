"""Unit tests for merge sizing, chunk checks and unregistered builds (no kmindex run)."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from pykmhelpers.core.kmindex_paths import chunk_complete, chunk_problems
from pykmhelpers.pipeline.index_ops import merging
from pykmhelpers.pipeline.index_ops.merging import (
    MergeLimits,
    footprint,
    max_inputs,
    merge_threads,
    merge_tree,
)

MiB = 2**20


class TestMergeThreads(unittest.TestCase):
    def test_capped_by_partitions(self):
        self.assertEqual(merge_threads(144, 4), 4)
        self.assertEqual(merge_threads(2, 4), 2)

    def test_unknown_partitions_keep_threads(self):
        self.assertEqual(merge_threads(8, 0), 8)
        self.assertEqual(merge_threads(0, 4), 1)


class TestMaxInputs(unittest.TestCase):
    def test_each_limit_can_bind(self):
        big = 10**15
        # 2 MiB per registered entry at m=10
        self.assertEqual(
            max_inputs(MergeLimits(ram=10 * 2 * 4**10, files=big, maps=big), 4, 10, 4),
            (10, "anonymous RAM"),
        )
        self.assertEqual(
            max_inputs(MergeLimits(ram=big, files=big, maps=1000 + 4 * 25), 4, 10, 4),
            (25, "vm.max_map_count"),
        )
        self.assertEqual(
            max_inputs(MergeLimits(ram=big, files=4 * 31, maps=big), 4, 10, 144),
            (30, "open files"),
        )

    def test_logan_g0_numbers(self):
        # 256 GiB, 200000 files, default max_map_count, P=4: maps bind
        k, limit = max_inputs(MergeLimits(256 * 2**30, 200000, 65530), 4, 10, 144)
        self.assertEqual((k, limit), (16132, "vm.max_map_count"))

    def test_fewer_than_two_inputs_is_an_error(self):
        with self.assertRaises(ValueError):
            max_inputs(MergeLimits(ram=10**12, files=2, maps=10**6), 4, 10, 1)


class TestMergeLimits(unittest.TestCase):
    def test_maps_from_limits(self):
        limits = MergeLimits.resolve('{"ram": 1000, "files": 10, "maps": 2000}')
        self.assertEqual(limits, MergeLimits(1000, 10, 2000))

    def test_maps_default_from_system(self):
        with mock.patch.object(merging, "_system_max_maps", return_value=12345):
            limits = MergeLimits.resolve('{"ram": 1000, "files": 10}')
        self.assertEqual(limits.maps, 12345)


class TestFootprint(unittest.TestCase):
    def test_matches_span_168_measurement(self):
        # 128 one-sample inputs, 128 registered, P=4, m=10, T=4: sampled
        # RssAnon 264 MiB and RssFile 3227 MiB (expe_merge/validation V3)
        fp = footprint([1] * 128, 128, 4, 10, 28547584, 4)
        self.assertAlmostEqual(fp["anon"] / MiB, 264, delta=264 * 0.05)
        self.assertAlmostEqual(fp["mapped"] / MiB, 3227, delta=3227 * 0.10)

    def test_fewer_threads_map_less(self):
        full = footprint([1] * 8, 8, 4, 10, 28547584, 4)["mapped"]
        one = footprint([1] * 8, 8, 4, 10, 28547584, 1)["mapped"]
        self.assertAlmostEqual(one * 4, full, delta=full * 0.01)


class TestMergeTree(unittest.TestCase):
    def names(self, n):
        return [f"c{i}" for i in range(n)]

    def test_single_step(self):
        steps = merge_tree("t", self.names(4), 4)
        self.assertEqual([(s.name, s.inputs) for s in steps], [("t", self.names(4))])

    def test_balanced_two_levels(self):
        steps = merge_tree("t", self.names(10), 4)
        self.assertEqual([len(s.inputs) for s in steps], [4, 3, 3, 3])
        self.assertEqual(steps[-1].name, "t")
        self.assertEqual(steps[-1].inputs, ["t__sub1_0", "t__sub1_1", "t__sub1_2"])

    def test_lone_input_moves_up(self):
        steps = merge_tree("t", self.names(5), 2)
        self.assertEqual(
            [(s.name, s.inputs) for s in steps],
            [
                ("t__sub1_0", ["c0", "c1"]),
                ("t__sub1_1", ["c2", "c3"]),
                ("t__sub2_0", ["t__sub1_0", "t__sub1_1"]),
                ("t", ["t__sub2_0", "c4"]),
            ],
        )

    def test_every_input_merged_once(self):
        for n, k in [(6552, 705), (6552, 61), (1472, 153), (7, 2)]:
            steps = merge_tree("t", self.names(n), k)
            self.assertTrue(all(2 <= len(s.inputs) <= k for s in steps[:-1]))
            consumed = [i for s in steps for i in s.inputs if i.startswith("c")]
            self.assertEqual(sorted(consumed), sorted(self.names(n)))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            merge_tree("t", self.names(3), 1)
        with self.assertRaises(ValueError):
            merge_tree("t", [], 4)


class TestChunkComplete(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kmhelpers_chunk_")
        os.makedirs(os.path.join(self.dir, "matrices"))
        os.makedirs(os.path.join(self.dir, "merge_infos"))
        for name in ("kmtricks.fof", "options.txt"):
            with open(os.path.join(self.dir, name), "w") as f:
                f.write("x\n")
        for p in range(4):
            self.write_matrix(p, 100)
            open(os.path.join(self.dir, "merge_infos", f"partition{p}.merge_info"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_matrix(self, p, size):
        with open(os.path.join(self.dir, "matrices", f"matrix_{p}.cmbf"), "wb") as f:
            f.write(b"\0" * size)

    def test_complete(self):
        self.assertTrue(chunk_complete(self.dir, 4))

    def test_missing_merge_info(self):
        os.remove(os.path.join(self.dir, "merge_infos", "partition1.merge_info"))
        self.assertEqual(chunk_problems(self.dir, 4), ["missing partition1.merge_info"])

    def test_missing_matrix(self):
        os.remove(os.path.join(self.dir, "matrices", "matrix_2.cmbf"))
        self.assertEqual(chunk_problems(self.dir, 4), ["missing matrix_2.cmbf"])

    def test_unequal_matrices(self):
        self.write_matrix(3, 50)
        self.assertFalse(chunk_complete(self.dir, 4))

    def test_empty_matrix(self):
        for p in range(4):
            self.write_matrix(p, 0)
        self.assertIn("empty matrix_0.cmbf", chunk_problems(self.dir, 4))

    def test_missing_directory(self):
        self.assertEqual(
            chunk_problems(os.path.join(self.dir, "nope"), 4), ["missing directory"]
        )


@unittest.skipUnless(shutil.which("kmtricks"), "kmtricks not in PATH")
class TestKmtricksWrapper(unittest.TestCase):
    def test_dry_run_command_matches_kmindex_build(self):
        from pykmhelpers.core.kmtricks_wrapper import KmtricksWrapper

        cmd = (
            KmtricksWrapper(dry_run=True)
            .pipeline(
                "/x/a.fof",
                "/x/data/a",
                k=25,
                minim_size=10,
                hard_min=1,
                bloom_size=28547520,
                nb_partitions=4,
                threads=144,
                compress_intermediate=True,
            )["command"]
            .split()
        )
        self.assertEqual(cmd[1], "pipeline")
        for opt, value in [
            ("--file", "/x/a.fof"),
            ("--run-dir", "/x/data/a"),
            ("--bloom-size", "28547520"),
            ("--minimizer-size", "10"),
            ("--nb-partitions", "4"),
            ("--mode", "hash:bf:bin"),
        ]:
            self.assertEqual(cmd[cmd.index(opt) + 1], value)
        self.assertIn("--static-repart", cmd)
        self.assertIn("--cpr", cmd)
        self.assertNotIn("--register-as", cmd)

    def test_abundance_mode(self):
        from pykmhelpers.core.kmtricks_wrapper import KmtricksWrapper

        cmd = (
            KmtricksWrapper(dry_run=True)
            .pipeline("/x/a.fof", "/x/data/a", bloom_size=1000, bitw=3)["command"]
            .split()
        )
        self.assertEqual(cmd[cmd.index("--bloom-size") + 1], "1000")
        self.assertEqual(cmd[cmd.index("--mode") + 1], "hash:bfc:bin")
        self.assertEqual(cmd[cmd.index("--bitw") + 1], "3")

    def test_presence_absence_without_bitw(self):
        from pykmhelpers.core.kmtricks_wrapper import KmtricksWrapper

        for bitw in (None, 0):
            cmd = (
                KmtricksWrapper(dry_run=True)
                .pipeline("/x/a.fof", "/x/data/a", bloom_size=1000, bitw=bitw)[
                    "command"
                ]
                .split()
            )
            self.assertEqual(cmd[cmd.index("--mode") + 1], "hash:bf:bin")
            self.assertNotIn("--bitw", cmd)

    def test_kmindex_build_mode_follows_bitw(self):
        """kmindex names the cells of an abundance index --nb-cell."""
        from pykmhelpers.core.kmindex_wrapper import KmindexWrapper

        with tempfile.TemporaryDirectory() as tmp:
            fof = os.path.join(tmp, "a.fof")
            with open(fof, "w") as f:
                f.write("a: /x/a.fa\n")
            registry = os.path.join(tmp, "registry")

            def build(**kwargs):
                return KmindexWrapper(dry_run=True).build(
                    input_fof_file=fof,
                    bloom_size=1000,
                    output_registry_path=registry,
                    register_as="a",
                    **kwargs,
                )["command"].split()

            pa = build()
            self.assertEqual(pa[pa.index("--bloom-size") + 1], "1000")
            self.assertNotIn("--nb-cell", pa)
            self.assertNotIn("--bitw", pa)

            ab = build(bitw=2)
            self.assertEqual(ab[ab.index("--nb-cell") + 1], "1000")
            self.assertEqual(ab[ab.index("--bitw") + 1], "2")
            self.assertNotIn("--bloom-size", ab)


if __name__ == "__main__":
    unittest.main()
