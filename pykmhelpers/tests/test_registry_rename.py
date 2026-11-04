"""Unit tests for `kmhelpers manage rename` (no kmindex needed)."""

import glob
import json
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from click.testing import CliRunner

from pykmhelpers.cli.kmhelpers import cli
from pykmhelpers.pipeline.index_ops import rename as rename_mod
from pykmhelpers.pipeline.index_ops.rename import index_shards


class RenameCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_rename_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.reg = self.tmp / "reg"
        self.shards = ["idx_g0", "idx_g1_p0", "idx_g1_p1", "other_g0"]
        for name in self.shards:
            (self.reg / name).mkdir(parents=True)
            (self.reg / name / "kmtricks.fof").write_text(f"{name} : /d/x.fa\n")
            (self.reg / "logs" / name).mkdir(parents=True)
            (self.reg / "logs" / name / "stats.yaml").write_text(yaml.safe_dump({"shard": name}))
        entries = {n: {"nb_samples": 1, "samples": [n]} for n in self.shards}
        (self.reg / "index.json").write_text(json.dumps({"path": str(self.reg), "index": entries}))
        self.runner = CliRunner()

    def rename(self, *args, yes=True):
        cmd = (["-Y"] if yes else []) + ["manage", "-r", str(self.reg), "rename", *args]
        return self.runner.invoke(cli, cmd)

    def entries(self) -> list[str]:
        return list(json.loads((self.reg / "index.json").read_text())["index"])

    def add_layout(self) -> Path:
        compose = self.tmp / "compose"
        (compose / "idx" / "s1").mkdir(parents=True)
        layout = {
            "type": "layout",
            "data": {
                "map": {
                    80: {"name": "idx_g0", "shards": [{"name": "idx_g0"}]},
                    85: {"name": "idx_g1", "shards": [{"name": "idx_g1_p0"}, {"name": "idx_g1_p1"}]},
                },
            },
        }
        (compose / "idx" / "layout.yaml").write_text(yaml.safe_dump(layout))
        return compose


class TestShard(RenameCase):
    def test_rename_shard(self):
        result = self.rename("idx_g0", "new_g0")
        self.assertEqual(result.exit_code, 0, result.output)
        # order kept, only the key changes
        self.assertEqual(self.entries(), ["new_g0", "idx_g1_p0", "idx_g1_p1", "other_g0"])
        self.assertTrue((self.reg / "new_g0" / "kmtricks.fof").is_file())
        self.assertFalse((self.reg / "idx_g0").exists())
        stats = yaml.safe_load((self.reg / "logs" / "new_g0" / "stats.yaml").read_text())
        self.assertEqual(stats["shard"], "new_g0")
        self.assertEqual(len(glob.glob(str(self.reg / "index.json.*.bak"))), 1)

    def test_symlinked_shard_keeps_target(self):
        target = self.tmp / "data" / "idx_g0"
        shutil.move(str(self.reg / "idx_g0"), target)
        os.symlink(target, self.reg / "idx_g0")
        result = self.rename("idx_g0", "new_g0")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(os.readlink(self.reg / "new_g0"), str(target))

    def test_unknown_shard(self):
        result = self.rename("zz", "new")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("'zz' not found", result.output)

    def test_existing_name_refused(self):
        result = self.rename("idx_g0", "other_g0")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("already registered", result.output)
        (self.reg / "stray").mkdir()
        result = self.rename("idx_g0", "stray")
        self.assertIn("already exists", result.output)
        self.assertEqual(self.entries(), self.shards)

    def test_reserved_name_refused(self):
        result = self.rename("idx_g0", "logs")
        self.assertNotEqual(result.exit_code, 0)
        self.assertTrue((self.reg / "idx_g0").is_dir())

    def test_refused_while_jobs_run(self):
        (self.reg / "assets" / "s1").mkdir(parents=True)
        (self.reg / "assets" / "s1" / "plan.yaml").write_text(yaml.safe_dump({"tasks": {}}))
        with mock.patch("pykmhelpers.pipeline.index_ops.rename.active_jobs", return_value=["1"]):
            result = self.rename("idx_g0", "new_g0")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("still queued or running", result.output)
        self.assertEqual(self.entries(), self.shards)

    def test_failure_undoes_renames(self):
        with mock.patch.object(rename_mod, "replace_atomically", side_effect=OSError("disk full")):
            result = self.rename("idx_g0", "new_g0")
        self.assertNotEqual(result.exit_code, 0)
        self.assertTrue((self.reg / "idx_g0").is_dir())
        self.assertTrue((self.reg / "logs" / "idx_g0").is_dir())
        self.assertEqual(self.entries(), self.shards)


class TestIndex(RenameCase):
    def test_index_shards(self):
        names = self.shards + ["idx_g2_extra", "idx2_g0"]
        self.assertEqual(index_shards(names, "idx"), ["idx_g0", "idx_g1_p0", "idx_g1_p1"])

    def test_rename_index(self):
        result = self.rename("--index", "idx", "virus")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.entries(), ["virus_g0", "virus_g1_p0", "virus_g1_p1", "other_g0"])
        for name in ("virus_g0", "virus_g1_p0", "virus_g1_p1"):
            self.assertTrue((self.reg / name).is_dir())
            self.assertTrue((self.reg / "logs" / name).is_dir())
        self.assertIn("--compose-dir", result.output)

    def test_unknown_index(self):
        result = self.rename("--index", "zz", "virus")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("No shard of index 'zz'", result.output)

    def test_index_needs_confirmation(self):
        result = self.rename("--index", "idx", "virus", yes=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.entries(), self.shards)

    def test_rename_with_layout(self):
        compose = self.add_layout()
        result = self.rename("--index", "idx", "virus", "--compose-dir", str(compose))
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse((compose / "idx").exists())
        layout = yaml.safe_load((compose / "virus" / "layout.yaml").read_text())
        spans = layout["data"]["map"]
        self.assertEqual(spans[85]["name"], "virus_g1")
        self.assertEqual([s["name"] for s in spans[85]["shards"]], ["virus_g1_p0", "virus_g1_p1"])
        self.assertTrue((compose / "virus" / "s1").is_dir())

    def test_compose_target_exists_renames_nothing(self):
        compose = self.add_layout()
        (compose / "virus").mkdir()
        result = self.rename("--index", "idx", "virus", "--compose-dir", str(compose))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(self.entries(), self.shards)

    def test_compose_dir_needs_index(self):
        result = self.rename("idx_g0", "new_g0", "--compose-dir", str(self.tmp))
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--compose-dir needs --index", result.output)


if __name__ == "__main__":
    unittest.main()
