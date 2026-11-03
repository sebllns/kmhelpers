"""Unit tests for `kmhelpers manage clean` (no kmindex needed)."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from click.testing import CliRunner

from pykmhelpers.cli.kmhelpers import cli
from pykmhelpers.pipeline.index_ops import clean
from pykmhelpers.pipeline.index_ops.clean import BUILD_LEFTOVERS

# Files of a kmtricks run that a published index needs
KEPT = (
    "matrices/matrix_0.cmbf",
    "hash.info",
    "repartition_gatb/repartition.minimRepart",
    "config_gatb/gatb.config",
    "options.txt",
    "kmtricks.fof",
    "build_infos.txt",
    "run_infos.txt",
    "fpr/partition_0.txt",
)


def fake_shard(path: Path) -> None:
    for name in KEPT:
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text("S1 : /d/S1.fa\n" if name == "kmtricks.fof" else "x")
    for name in BUILD_LEFTOVERS:
        (path / name).mkdir()
        (path / name / "f").write_bytes(b"x" * 100)


class CleanCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_clean_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.reg = self.tmp / "reg"
        for shard in ("a", "b"):
            fake_shard(self.reg / shard)
        (self.reg / "index.json").write_text(json.dumps({"index": {"a": {}, "b": {}}}))
        self.runner = CliRunner()

    def run_clean(self, *args, yes=True):
        cmd = (["-Y"] if yes else []) + ["manage", "-r", str(self.reg), "clean", *args]
        return self.runner.invoke(cli, cmd)

    def add_session(self, session: str, shard: str, samples: list[str]) -> Path:
        assets = self.reg / "assets" / session
        (assets / shard).mkdir(parents=True)
        (assets / shard / f"{shard}_{session}.fof").write_text(
            "".join(f"{s} : /d/{s}.fa\n" for s in samples)
        )
        task = {"shard": shard, "dir": f"{shard}/", "chunks": {f"{shard}_{session}": {}}}
        (assets / "plan.yaml").write_text(yaml.safe_dump({"tasks": {shard: task}}))
        return assets


class TestShards(CleanCase):
    def test_removes_leftovers_keeps_index(self):
        result = self.run_clean()
        self.assertEqual(result.exit_code, 0, result.output)
        for shard in ("a", "b"):
            for name in BUILD_LEFTOVERS:
                self.assertFalse((self.reg / shard / name).exists(), name)
            for name in KEPT:
                self.assertTrue((self.reg / shard / name).exists(), name)
        self.assertIn("Freed", result.output)

    def test_dry_run_removes_nothing(self):
        result = self.run_clean("-n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("a/superkmers", result.output)
        self.assertTrue((self.reg / "a" / "superkmers").is_dir())

    def test_shard_filter(self):
        result = self.run_clean("--sh", "a")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse((self.reg / "a" / "superkmers").exists())
        self.assertTrue((self.reg / "b" / "superkmers").is_dir())

    def test_unknown_shard_fails(self):
        result = self.run_clean("--sh", "zz")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Not registered: zz", result.output)

    def test_nothing_to_clean(self):
        self.run_clean()
        result = self.run_clean()
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Nothing to clean", result.output)

    def test_no_terminal_refuses_without_yes(self):
        result = self.run_clean(yes=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("-Y", result.output)
        self.assertTrue((self.reg / "a" / "superkmers").is_dir())


class TestAssets(CleanCase):
    def test_finished_session_removed_pending_kept(self):
        done = self.add_session("s1", "a", ["S1"])
        pending = self.add_session("s2", "b", ["S1", "S9"])
        result = self.run_clean("--assets")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertFalse(done.exists())
        self.assertTrue(pending.exists())
        self.assertIn("Kept assets/s2: not published: b", result.output)

    def test_active_session_kept(self):
        done = self.add_session("s1", "a", ["S1"])
        with mock.patch.object(clean, "active_jobs", return_value=["123"]):
            result = self.run_clean("--assets")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(done.exists())
        self.assertIn("queued or running", result.output)


class TestLogs(CleanCase):
    def setUp(self):
        super().setUp()
        logs = self.reg / "logs"
        (logs / "a").mkdir(parents=True)
        (logs / "slurm").mkdir()
        for name in ("a/a_s1.log", "a/a_s1.log.prev", "a/publish.log", "a/stats.yaml",
                     "a/a_s1.stats.json", "slurm/job_1.out", "kmhelpers_plan_1.yaml"):
            (logs / name).write_text("x")
        self.logs = logs

    def test_logs_removed_stats_kept(self):
        result = self.run_clean("--logs")
        self.assertEqual(result.exit_code, 0, result.output)
        remaining = sorted(str(p.relative_to(self.logs)) for p in self.logs.rglob("*") if p.is_file())
        self.assertEqual(remaining, ["a/a_s1.stats.json", "a/stats.yaml"])

    def test_refused_while_jobs_run(self):
        self.add_session("s1", "a", ["S1"])
        with mock.patch.object(clean, "active_jobs", return_value=["123"]):
            result = self.run_clean("--logs")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("s1", result.output)
        self.assertTrue((self.logs / "a" / "a_s1.log").exists())


if __name__ == "__main__":
    unittest.main()
