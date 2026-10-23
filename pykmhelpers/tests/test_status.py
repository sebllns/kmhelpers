"""Unit tests for the step states and the progress tree of a build (no kmindex run)."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from pykmhelpers.cli.notify import ExitNotifier
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import MERGE
from pykmhelpers.pipeline.index_ops.status import (
    CANCELLED,
    FAILED,
    LOST,
    PENDING,
    RUNNING,
    SUCCESS,
    BuildState,
    overall,
    render,
)

PARTITIONS = 2


class StatusCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.paths = BuildPaths(str(self.tmp / "build"), "s1")
        self.task = {
            "shard": "idx_g0",
            "dir": "idx_g0/",
            "partitions": PARTITIONS,
            "chunks": {"idx_g0_s1_chunk0": {"samples": 1}, "idx_g0_s1_chunk1": {"samples": 1}},
            "merge": {"script": "merge.sh"},
            "jobs": {
                "idx_g0_j0": ["idx_g0_s1_chunk0"],
                "idx_g0_j1": ["idx_g0_s1_chunk1"],
                "idx_g0_merge": [MERGE],
            },
        }
        self.plan = {"tasks": {"idx_g0_s1": self.task}}
        self.state = BuildState(self.plan, self.paths)
        task_dir = Path(self.paths.task("idx_g0"))
        task_dir.mkdir(parents=True)
        for n in range(2):
            (task_dir / f"idx_g0_s1_chunk{n}.fof").write_text(f"s{n}: /data/s{n}.fa\n")

    def complete_run(self, run):
        d = Path(self.paths.run(run))
        (d / "matrices").mkdir(parents=True)
        for name in ("run_infos.txt", "kmtricks.fof", "options.txt"):
            (d / name).write_text("x\n")
        for p in range(PARTITIONS):
            (d / "matrices" / f"matrix_{p}.cmbf").write_bytes(b"\0" * 10)

    def publish(self, samples):
        Path(self.paths.build_dir, "index.json").write_text(json.dumps({"index": {"idx_g0": {}}}))
        shard = Path(self.paths.shard("idx_g0"))
        shard.mkdir(parents=True)
        (shard / "kmtricks.fof").write_text("".join(f"{s} : /x\n" for s in samples))

    def status(self, step, job_of=None, alive=None):
        return self.state.step_status(self.task, step, job_of, alive)


class TestStepStatus(StatusCase):
    def test_pending(self):
        self.assertEqual(self.status("idx_g0_s1_chunk0"), (PENDING, ""))
        self.assertEqual(self.status("idx_g0_s1_chunk0", "18_0"), (PENDING, "job 18_0"))
        status, detail = self.status("idx_g0_s1_chunk0", "18_0", alive=lambda job: False)
        self.assertEqual(status, PENDING)
        self.assertIn("ended without running it", detail)

    def test_success_from_the_build_directory(self):
        """A complete run is SUCCESS, whatever its state file says."""
        self.state.write_state(self.task, "idx_g0_s1_chunk0", FAILED, error="old")
        self.complete_run("idx_g0_s1_chunk0")
        self.assertEqual(self.status("idx_g0_s1_chunk0")[0], SUCCESS)
        self.assertEqual(self.status(MERGE)[0], PENDING)

    def test_published_task_is_success(self):
        self.publish(["s0", "s1"])
        self.assertEqual(self.status(MERGE)[0], SUCCESS)
        self.assertEqual(self.status("idx_g0_s1_chunk1")[0], SUCCESS)

    def test_failed_and_cancelled(self):
        log = os.path.join(self.paths.logs, "idx_g0", "idx_g0_s1_chunk0.log")
        self.state.write_state(self.task, "idx_g0_s1_chunk0", FAILED, log=log, error="exit 3")
        status, detail = self.status("idx_g0_s1_chunk0")
        self.assertEqual(status, FAILED)
        self.assertEqual(detail, "log: logs/idx_g0/idx_g0_s1_chunk0.log, exit 3")
        self.state.write_state(self.task, MERGE, CANCELLED, error="SIGTERM")
        self.assertEqual(self.status(MERGE), (CANCELLED, "SIGTERM"))

    def test_running_then_lost(self):
        with mock.patch.dict(os.environ, {"SLURM_ARRAY_JOB_ID": "18", "SLURM_ARRAY_TASK_ID": "1"}):
            self.state.write_state(self.task, "idx_g0_s1_chunk1", RUNNING)
        status, detail = self.status("idx_g0_s1_chunk1")
        self.assertEqual(status, RUNNING)
        self.assertTrue(detail.startswith("job 18_1, "), detail)
        self.assertEqual(self.status("idx_g0_s1_chunk1", alive=lambda job: True)[0], RUNNING)
        status, detail = self.status("idx_g0_s1_chunk1", alive=lambda job: False)
        self.assertEqual(status, LOST)
        self.assertIn("job 18_1 ended without a status", detail)


class TestProgress(StatusCase):
    def test_tree_and_file(self):
        self.complete_run("idx_g0_s1_chunk0")
        self.state.write_state(self.task, "idx_g0_s1_chunk1", FAILED, error="boom")
        sub = Path(self.paths.assets) / "slurm"
        sub.mkdir(parents=True)
        (sub / "submitted.tsv").write_text("idx_g0_merge\t17\nidx_g0_merge\t19\n")

        tree = self.state.write_progress()
        steps = tree["shards"]["idx_g0"]
        self.assertEqual(steps["idx_g0_s1_chunk0"], SUCCESS)
        self.assertEqual(steps["idx_g0_s1_chunk1"], "FAILED (boom)")
        self.assertEqual(steps[MERGE], "PENDING (job 19)")  # the last submission
        self.assertEqual(tree["summary"]["failed"], 1)
        self.assertEqual(overall(tree), FAILED)
        on_disk = yaml.safe_load((Path(self.paths.assets) / "progress.yaml").read_text())
        self.assertEqual(on_disk["shards"], tree["shards"])

        text = render(tree)
        self.assertTrue(text.startswith("FAILED: 0/1 shard(s) done, 1 failed"))
        self.assertIn("  merge: PENDING (job 19)", text)
        self.assertNotIn("idx_g0", render(tree, ["other"]).split("\n", 1)[-1])

    def test_done(self):
        self.publish(["s0", "s1"])
        self.assertEqual(overall(self.state.progress()), SUCCESS)


class TestNotifier(unittest.TestCase):
    def notifier(self, level, final=True):
        with mock.patch("pykmhelpers.cli.notify.atexit.register") as register:
            n = ExitNotifier("apply", "me@example.com", level, final=final)
        n.progress = lambda shards=None: f"tree of {shards or 'all'}"
        return n, register

    def test_shard_level(self):
        n, register = self.notifier("shard")
        register.assert_called_once()
        with mock.patch("pykmhelpers.cli.notify.mail") as mail:
            n.shard_end("idx_g0", SUCCESS)
        to, subject, body, _ = mail.call_args.args
        self.assertEqual(subject, "[kmhelpers apply] idx_g0 SUCCESS")
        self.assertIn("tree of ['idx_g0']", body)

    def test_global_level_has_no_shard_mail(self):
        n, _ = self.notifier("global")
        with mock.patch("pykmhelpers.cli.notify.mail") as mail:
            n.shard_end("idx_g0", SUCCESS)
        mail.assert_not_called()

    def test_final_mail_carries_the_progress(self):
        n, _ = self.notifier("global")
        n.status = "FAILED"
        with mock.patch("pykmhelpers.cli.notify.mail") as mail:
            n._send()
        _, subject, body, _ = mail.call_args.args
        self.assertEqual(subject, "[kmhelpers apply] FAILED")
        self.assertIn("tree of all", body)

    def test_no_final_mail(self):
        _, register = self.notifier("shard", final=False)
        register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
