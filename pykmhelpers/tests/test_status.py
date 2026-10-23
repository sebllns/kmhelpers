"""Unit tests for the step states and the progress tree of a build (no kmindex run)."""

import io
import json
import os
import shutil
import socket
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import yaml

from pykmhelpers.cli.notify import ExitNotifier
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import MERGE
from pykmhelpers.pipeline.index_ops.progress import ShardDisplay
from pykmhelpers.pipeline.index_ops.status import (
    CANCELLED,
    FAILED,
    LOST,
    PENDING,
    RUNNING,
    SUCCESS,
    BuildState,
    ShardProgress,
    active_jobs,
    duration,
    overall,
    render,
    shard_line,
    shard_progress,
    short_step,
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


class TestShardLine(StatusCase):
    def running(self, step, minutes):
        started = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        path = Path(self.state.state_path(self.task, step))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": RUNNING, "job": "1_0", "started": started}))

    def test_shard_progress(self):
        self.complete_run("idx_g0_s1_chunk0")
        self.running("idx_g0_s1_chunk1", 3)
        p = shard_progress(self.state, self.task)
        self.assertEqual((p.state, p.done, p.total), (RUNNING, 1, 3))
        self.assertEqual([s for s, _ in p.running], ["idx_g0_s1_chunk1"])
        self.assertTrue(p.shown)

    def test_not_started_is_not_shown(self):
        self.assertFalse(shard_progress(self.state, self.task).shown)

    def test_line_shows_three_running_oldest_first(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        running = [(f"idx_g0_s1_chunk{n}", now - timedelta(minutes=m)) for n, m in
                   [(5, 2), (2, 9), (8, 1), (1, 5), (3, 4)]]
        running.sort(key=lambda r: r[1])
        p = ShardProgress("idx_g0", RUNNING, 6, 11, running, started=now - timedelta(minutes=10))
        line = shard_line(p, 6, now, "⣾")
        self.assertIn("[■■■■■■■     ] 6/11", line)
        self.assertIn("(10m0s)", line)
        self.assertIn("5 running: chunk2 (9m0s), chunk1 (5m0s), chunk3 (4m0s), ...", line)

    def test_line_merge_success_failure(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        merging = ShardProgress("g", RUNNING, 10, 11, [("merge", now - timedelta(seconds=184))])
        self.assertTrue(shard_line(merging, 1, now).endswith("merge (3m4s)"))
        done = ShardProgress("g", SUCCESS, 2, 2, started=now - timedelta(hours=1, minutes=2),
                             finished=now)
        self.assertIn("✔ g  [■■■■■■■■■■■■] 2/2", shard_line(done, 1, now))
        self.assertIn("(1h02m)", shard_line(done, 1, now))
        self.assertIn("\033[32mSUCCESS", shard_line(done, 1, now, color=True))
        failed = ShardProgress("g", FAILED, 3, 9, [("idx_g_s1_chunk4", now)],
                               failed=(FAILED, "idx_g_s1_chunk3", "log: x.log"))
        line = shard_line(failed, 1, now)
        self.assertIn("✘ g", line)
        self.assertIn("FAILED chunk3 (log: x.log), 1 still running", line)
        self.assertNotIn("\033", line)

    def test_short_step(self):
        self.assertEqual(short_step("idx_g0_s1_chunk12"), "chunk12")
        self.assertEqual(short_step("merge"), "merge")
        self.assertEqual(short_step("idx_g0_s1"), "run")
        self.assertEqual((duration(52), duration(483), duration(3725)), ("52s", "8m3s", "1h02m"))

    def test_display_not_live_prints_changes(self):
        out = io.StringIO()
        display = ShardDisplay(self.state, live=False, stream=out).start()
        # not started: no shard line, the waiting message once
        self.assertIn("waiting for the first step", out.getvalue())
        self.running("idx_g0_s1_chunk0", 1)
        display.update()
        display.update()  # nothing changed: nothing printed
        self.complete_run("idx_g0_s1_chunk0")
        display.update()
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 3, lines)
        self.assertIn("1/3", lines[2])
        self.assertNotIn("\033", out.getvalue())

    def test_display_waits_with_a_message(self):
        out = io.StringIO()
        display = ShardDisplay(self.state, live=True, stream=out)
        display.update()
        self.assertIn("waiting for the first step to start (1 shard pending)", out.getvalue())
        out = io.StringIO()
        display = ShardDisplay(self.state, live=False, stream=out)
        display.update()
        display.update()
        self.assertEqual(out.getvalue().count("waiting for the first step"), 1)

    def test_display_live_redraws(self):
        out = io.StringIO()
        self.running("idx_g0_s1_chunk0", 1)
        display = ShardDisplay(self.state, live=True, stream=out)
        display.update()
        display.update()
        self.assertIn("\033[1F\033[J", out.getvalue())


class TestActiveJobs(StatusCase):
    def submitted(self, *ids):
        sub = Path(self.paths.assets) / "slurm"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "submitted.tsv").write_text("".join(f"job{n}\t{i}\n" for n, i in enumerate(ids)))

    def test_slurm_jobs_still_in_squeue(self):
        self.submitted("10_0", "11")
        alive = {"10_0": True, "11": False}
        with mock.patch("pykmhelpers.pipeline.index_ops.status.shutil.which", return_value="/x/squeue"), \
                mock.patch("pykmhelpers.pipeline.index_ops.status.squeue_alive", side_effect=alive.get):
            self.assertEqual(active_jobs(self.state), ["10_0"])

    def test_no_squeue_no_slurm_check(self):
        self.submitted("10_0")
        with mock.patch("pykmhelpers.pipeline.index_ops.status.shutil.which", return_value=None):
            self.assertEqual(active_jobs(self.state), [])

    def test_local_apply_still_running(self):
        path = Path(self.state.state_path(self.task, "idx_g0_s1_chunk0"))
        path.parent.mkdir(parents=True, exist_ok=True)
        node = socket.gethostname()
        with mock.patch("pykmhelpers.pipeline.index_ops.status.shutil.which", return_value=None):
            path.write_text(json.dumps({"status": RUNNING, "job": f"pid {os.getpid()}", "node": node}))
            self.assertEqual(active_jobs(self.state), [f"pid {os.getpid()}"])
            path.write_text(json.dumps({"status": RUNNING, "job": "pid 999999999", "node": node}))
            self.assertEqual(active_jobs(self.state), [])
            path.write_text(json.dumps({"status": RUNNING, "job": f"pid {os.getpid()}", "node": "other"}))
            self.assertEqual(active_jobs(self.state), [])


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
