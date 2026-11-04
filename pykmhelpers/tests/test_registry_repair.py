"""Unit tests for `kmhelpers manage check --autorepair` (no kmindex needed: --nq)."""

import glob
import json
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

from pykmhelpers.cli.kmhelpers import cli
from pykmhelpers.pipeline.index_ops.repair import ABSOLUTE, RELINK, REMOVE, ROOT, plan_repairs

PARTITIONS = 2


def fake_index(path: Path, samples: list[str]) -> str:
    """A folder passing check_index_structure, holding ``samples``."""
    for name in ("build_infos.txt", "hash.info", "options.txt",
                 "config_gatb/gatb.config", "repartition_gatb/repartition.minimRepart"):
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text("x")
    (path / "matrices").mkdir(exist_ok=True)
    for p in range(PARTITIONS):
        (path / "matrices" / f"matrix_{p}.cmbf").write_bytes(b"x" * 64)
    (path / "kmtricks.fof").write_text("".join(f"{s} : /d/{s}.fa\n" for s in samples))
    return str(path)


def entry(samples: list[str]) -> dict:
    """An index.json entry, as kmindex register writes it."""
    return {
        "nb_partitions": PARTITIONS,
        "samples": samples,
        "nb_samples": len(samples),
        "bloom_size": 1000,
        "smer_size": 21,
        "minim_size": 10,
        "index_size": 128,
        "bw": 1,
        "sha1": "0",
        "kmindex_version": "0.6.0",
        "kmtricks_version": "1.5.1",
    }


class RepairCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_repair_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.reg = self.tmp / "reg"
        self.reg.mkdir()
        self.data = self.tmp / "data"
        self.data.mkdir()
        self.runner = CliRunner()
        # the CLI logs to the stream of a finished CliRunner: mute it
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def write_json(self, entries: dict, root: str | None = None) -> None:
        root = root or os.path.realpath(self.reg)
        (self.reg / "index.json").write_text(json.dumps({"path": root, "index": entries}))

    def load_json(self) -> dict:
        return json.loads((self.reg / "index.json").read_text())

    def check(self, *args, yes=True):
        cmd = (["-Y"] if yes else []) + ["manage", "-r", str(self.reg), "check", "--nq", *args]
        return self.runner.invoke(cli, cmd)

    def kinds(self, **kw) -> dict:
        repairs, _ = plan_repairs(str(self.reg), **kw)
        return {r.shard: r.kind for r in repairs}

    def backups(self) -> list[str]:
        return glob.glob(str(self.reg / "index.json.*.bak"))


class TestRepairs(RepairCase):
    def test_healthy_registry(self):
        fake_index(self.reg / "a", ["S1"])
        self.write_json({"a": entry(["S1"])})
        result = self.check("--autorepair")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Nothing to repair", result.output)
        self.assertEqual(self.backups(), [])

    def test_stale_root_path_fixed_with_backup(self):
        fake_index(self.reg / "a", ["S1"])
        self.write_json({"a": entry(["S1"])}, root="/old/place")
        self.assertEqual(self.kinds(), {None: ROOT})
        result = self.check("--autorepair")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.load_json()["path"], os.path.realpath(self.reg))
        (backup,) = self.backups()
        self.assertEqual(json.loads(Path(backup).read_text())["path"], "/old/place")

    def test_relative_link_made_absolute(self):
        target = fake_index(self.data / "a", ["S1"])
        os.symlink("../data/a", self.reg / "a")
        self.write_json({"a": entry(["S1"])})
        self.assertEqual(self.kinds(), {"a": ABSOLUTE})
        result = self.check("--autorepair")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(os.readlink(self.reg / "a"), os.path.realpath(target))

    def test_dangling_link_found_in_search_dir(self):
        moved = fake_index(self.data / "group" / "a", ["S1", "S2"])
        os.symlink("/gone/a", self.reg / "a")
        self.write_json({"a": entry(["S1", "S2"])})
        result = self.check("--autorepair", "--search", str(self.data))
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(os.readlink(self.reg / "a"), os.path.realpath(moved))
        self.assertIn("a", self.load_json()["index"])

    def test_other_samples_not_linked(self):
        fake_index(self.data / "a", ["S1", "S9"])
        os.symlink("/gone/a", self.reg / "a")
        self.write_json({"a": entry(["S1", "S2"])})
        self.assertEqual(self.kinds(search_dirs=[str(self.data)]), {"a": REMOVE})

    def test_found_in_old_root(self):
        old = self.tmp / "old_reg"
        fake_index(old / "a", ["S1"])
        self.write_json({"a": entry(["S1"])}, root=str(old))
        self.assertEqual(self.kinds(), {None: ROOT, "a": RELINK})

    def test_found_in_previous(self):
        fake_index(self.reg / "work" / "s1" / "previous" / "a", ["S1"])
        self.write_json({"a": entry(["S1"])})
        self.assertEqual(self.kinds(), {"a": RELINK})

    def test_lost_shard_removed(self):
        fake_index(self.reg / "b", ["S2"])
        os.symlink("/gone/a", self.reg / "a")
        self.write_json({"a": entry(["S1"]), "b": entry(["S2"])})
        result = self.check("--autorepair")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(list(self.load_json()["index"]), ["b"])
        self.assertFalse(os.path.lexists(self.reg / "a"))
        self.assertEqual(len(self.backups()), 1)

    def test_removal_refused_without_terminal(self):
        os.symlink("/gone/a", self.reg / "a")
        self.write_json({"a": entry(["S1"])})
        result = self.check("--autorepair", yes=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("a", self.load_json()["index"])
        self.assertTrue(os.path.islink(self.reg / "a"))
        self.assertEqual(self.backups(), [])

    def test_shard_filter(self):
        os.symlink("/gone/a", self.reg / "a")
        os.symlink("/gone/b", self.reg / "b")
        self.write_json({"a": entry(["S1"]), "b": entry(["S2"])})
        self.assertEqual(self.kinds(shards=["a"]), {"a": REMOVE})

    def test_unregistered_folder_reported(self):
        fake_index(self.reg / "a", ["S1"])
        fake_index(self.reg / "orphan", ["S3"])
        self.write_json({"a": entry(["S1"])})
        _, unregistered = plan_repairs(str(self.reg))
        self.assertEqual(unregistered, ["orphan"])

    def test_check_reports_relative_link(self):
        fake_index(self.data / "a", ["S1"])
        os.symlink("../data/a", self.reg / "a")
        self.write_json({"a": entry(["S1"])})
        result = self.check()
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("a: relative link ../data/a", result.output)

    def test_check_reports_samples_mismatch(self):
        fake_index(self.reg / "a", ["S1", "S2"])
        self.write_json({"a": entry(["S2", "S1"])})
        result = self.check()
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("a: samples of index.json differ from kmtricks.fof", result.output)
        self.assertIn("0 OK, 1 FAILED", result.output)

    def test_check_healthy_json(self):
        fake_index(self.reg / "a", ["S1"])
        self.write_json({"a": entry(["S1"])})
        result = self.check()
        self.assertEqual(result.exit_code, 0, result.output)

    def test_search_needs_autorepair(self):
        self.write_json({})
        result = self.check("--search", str(self.data))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--search needs --autorepair", result.output)


if __name__ == "__main__":
    unittest.main()
