"""Unit tests for the stats of the runs and shards (no kmtricks needed)."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from pykmhelpers.pipeline.index_ops.stats import (
    fpr_summary,
    run_stats,
    sample_fpr,
    write_run_stats,
    write_shard_stats,
)


def fake_run(path: Path, samples: list[str], fpr: list[list[float]], superkmers=True) -> str:
    """A complete kmtricks run: one fpr file per partition, one value per sample."""
    (path / "matrices").mkdir(parents=True)
    (path / "fpr").mkdir()
    (path / "run_infos.txt").write_text("Time: 31 seconds\nMemory: 1476.222656MB\n")
    (path / "options.txt").write_text("Options: dir=x, nb_parts=0, bloom_size=1000, keep_tmp=0")
    (path / "kmtricks.fof").write_text("".join(f"{s} : /d/{s}.fa\n" for s in samples))
    for p, values in enumerate(fpr):
        (path / "matrices" / f"matrix_{p}.cmbf").write_bytes(b"x" * 100)
        (path / "fpr" / f"partition_{p}.txt").write_text("".join(f"{v}\n" for v in values))
    if superkmers:
        (path / "superkmers").mkdir()
        (path / "superkmers" / "s.skp").write_bytes(b"x" * 1000)
    return str(path)


class TestRunStats(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_stats_"))
        self.run = fake_run(self.tmp / "runs" / "a_chunk0", ["S1", "S2"], [[0.004, 0.02], [0.006, 0.04]])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_stats(self):
        stats = run_stats(self.run)
        self.assertEqual(stats["run"], "a_chunk0")
        self.assertEqual(stats["duration_s"], 31.0)
        self.assertEqual(stats["peak_rss_mb"], 1476.2)
        self.assertEqual(stats["samples"], 2)
        self.assertEqual(stats["partitions"], 2)
        self.assertEqual(stats["bloom_size"], 1000)
        self.assertEqual(stats["bf_bytes"], 200)
        # superkmers included: the peak of the run
        self.assertGreater(stats["disk_bytes"], 1200)
        self.assertNotIn("fpr", stats)

    def test_fpr_per_sample(self):
        self.assertEqual(sample_fpr(self.run, ["S1", "S2"]), {"S1": 0.005, "S2": 0.03})
        stats = run_stats(self.run, fpr=True)
        self.assertEqual(stats["fpr"], {"S1": 0.005, "S2": 0.03})
        self.assertEqual(stats["fpr_above_1pct"], ["S2"])
        self.assertEqual(stats["fpr_max_sample"], "S2")
        self.assertAlmostEqual(stats["fpr_mean"], 0.0175)

    def test_fpr_count_must_match_the_samples(self):
        with self.assertRaises(ValueError):
            sample_fpr(self.run, ["S1"])

    def test_fpr_summary_empty(self):
        self.assertEqual(fpr_summary({}), {})

    def test_reused_run_keeps_its_peak(self):
        out = str(self.tmp / "logs" / "a" / "a_chunk0.stats.json")
        first = write_run_stats(self.run, out)
        shutil.rmtree(Path(self.run) / "superkmers")
        self.assertEqual(write_run_stats(self.run, out)["disk_bytes"], first["disk_bytes"])
        # asking for the FP rates reads the run again
        self.assertIn("fpr", write_run_stats(self.run, out, fpr=True))


class TestMonitorFolding(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_monitor_stats_"))
        self.logs = self.tmp / "logs" / "a"
        self.logs.mkdir(parents=True)
        self.shard = self.tmp / "a"
        self.shard.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def monitor(self, name: str, **fields) -> None:
        base = dict.fromkeys(("wall_s", "cpu_user_s", "cpu_sys_s", "peak_rss_max_proc_kb",
                              "peak_rss_tree_kb", "peak_open_files", "peak_disk_bytes",
                              "peak_disk_inodes", "final_disk_bytes"), 0)
        (self.logs / f"{name}.monitor.json").write_text(json.dumps({**base, **fields}))

    def test_runs_and_merges_are_folded(self):
        for run, cpu, fds, disk in (("a_chunk0", 10, 300, 5000), ("a_chunk1", 30, 900, 7000)):
            self.monitor(run, wall_s=cpu / 2, cpu_user_s=cpu, peak_open_files=fds, peak_disk_bytes=disk,
                         peak_rss_max_proc_kb=1000)
            (self.logs / f"{run}.stats.json").write_text(json.dumps({"run": run, "samples": 1}))
        # write_run_stats folds the monitor file of the run
        from pykmhelpers.pipeline.index_ops.stats import load_monitor, monitor_path

        self.assertEqual(monitor_path(str(self.logs / "a_chunk0.stats.json")),
                         str(self.logs / "a_chunk0.monitor.json"))
        stats_files = []
        for run in ("a_chunk0", "a_chunk1"):
            path = self.logs / f"{run}.stats.json"
            path.write_text(json.dumps({"run": run, "samples": 1,
                                        "monitor": load_monitor(monitor_path(str(path)))}))
            stats_files.append(str(path))
        self.monitor("merge_a", wall_s=60, cpu_user_s=200, peak_rss_tree_kb=5000, peak_open_files=40)
        data = write_shard_stats(str(self.logs / "stats.yaml"), "a", "initial", stats_files, 70, str(self.shard))
        summary = data["summary"]
        self.assertEqual(summary["builds"]["monitored"], 2)
        self.assertEqual(summary["builds"]["cpu_s"], 40)
        self.assertEqual(summary["builds"]["peak_open_files"], 900)
        self.assertEqual(summary["builds"]["peak_disk_bytes"], 7000)
        self.assertEqual(summary["merges"]["cpu_s"], 200)
        self.assertEqual(summary["merges"]["peak_rss_kb"], 5000)
        self.assertIn("a", data["sessions"]["initial"]["publish"]["merges"])


class TestShardStats(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_stats_"))
        self.shard = self.tmp / "a"
        self.shard.mkdir()
        self.out = str(self.tmp / "logs" / "a" / "stats.yaml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stats_file(self, run: str, **fields) -> str:
        path = self.tmp / "logs" / "a" / f"{run}.stats.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"run": run, **fields}))
        return str(path)

    def test_sessions_are_folded(self):
        (self.shard / "kmtricks.fof").write_text("S1 : x\nS2 : y\n")
        c0 = self.stats_file(
            "a_chunk0", duration_s=10, peak_rss_mb=100, disk_bytes=5000, samples=1,
            bloom_size=1000, fpr={"S1": 0.005},
        )
        c1 = self.stats_file(
            "a_chunk1", duration_s=20, peak_rss_mb=300, disk_bytes=7000, samples=1,
            bloom_size=1000, fpr={"S2": 0.02},
        )
        data = write_shard_stats(self.out, "a", "initial", [c0, c1], 5, str(self.shard))
        summary = data["summary"]
        self.assertEqual(summary["samples"], 2)
        self.assertEqual(summary["chunks"], 2)
        self.assertEqual(summary["duration_s"], 35)
        self.assertEqual(summary["peak_rss_mb"], 300)
        self.assertEqual(summary["peak_disk_bytes"], 7000)
        self.assertEqual(summary["fpr_above_1pct"], ["S2"])
        self.assertNotIn("fpr", data["sessions"]["initial"]["chunks"]["a_chunk0"])

        # an update: the samples of the first session keep their FP rate
        (self.shard / "kmtricks.fof").write_text("S1 : x\nS2 : y\nS3 : z\n")
        c2 = self.stats_file("a_p1", duration_s=1, disk_bytes=10, samples=1, fpr={"S3": 0.5})
        write_shard_stats(self.out, "a", "update", [c2], 2, str(self.shard))
        with open(self.out) as f:
            data = yaml.safe_load(f)
        self.assertEqual(list(data["sessions"]), ["initial", "update"])
        self.assertEqual(data["summary"]["samples"], 3)
        self.assertEqual(data["summary"]["duration_s"], 38)
        self.assertEqual(data["summary"]["fpr_above_1pct"], ["S2", "S3"])
        self.assertEqual(set(data["fpr_samples"]), {"S1", "S2", "S3"})

    def test_missing_run_stats_are_skipped(self):
        data = write_shard_stats(
            self.out, "a", "initial", [str(self.tmp / "none.json")], None, str(self.shard)
        )
        self.assertEqual(data["sessions"]["initial"]["chunks"], {})
        self.assertNotIn("duration_s", data["sessions"]["initial"]["publish"])


if __name__ == "__main__":
    unittest.main()
