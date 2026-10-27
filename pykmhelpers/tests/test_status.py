"""Unit tests for the step states and the progress tree of a build (no kmindex run)."""

import io
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import yaml

from pykmhelpers.cli.notify import ExitNotifier
from pykmhelpers.core.wrapper import Wrapper
from pykmhelpers.pipeline.index_ops import status as status_mod
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import PUBLISH
from pykmhelpers.pipeline.index_ops.progress import ShardDisplay
from pykmhelpers.pipeline.index_ops.run_log import parse_kmtricks_log
from pykmhelpers.pipeline.index_ops.status import (
    CANCELLED,
    FAILED,
    LOST,
    PENDING,
    RUNNING,
    SUCCESS,
    BuildState,
    ShardProgress,
    StepDetail,
    _rss_bytes,
    active_jobs,
    detail_text,
    duration,
    human_bytes,
    kmtricks_phase,
    overall,
    phase_text,
    ram_text,
    render,
    shard_line,
    shard_progress,
    short_step,
    slurm_ram,
    step_details,
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
            "publish": {"script": "publish.sh"},
            "jobs": {
                "idx_g0_j0": ["idx_g0_s1_chunk0"],
                "idx_g0_j1": ["idx_g0_s1_chunk1"],
                "idx_g0_publish": [PUBLISH],
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
        self.assertEqual(self.status(PUBLISH)[0], PENDING)

    def test_published_task_is_success(self):
        self.publish(["s0", "s1"])
        self.assertEqual(self.status(PUBLISH)[0], SUCCESS)
        self.assertEqual(self.status("idx_g0_s1_chunk1")[0], SUCCESS)

    def test_failed_and_cancelled(self):
        log = os.path.join(self.paths.logs, "idx_g0", "idx_g0_s1_chunk0.log")
        self.state.write_state(self.task, "idx_g0_s1_chunk0", FAILED, log=log, error="exit 3")
        status, detail = self.status("idx_g0_s1_chunk0")
        self.assertEqual(status, FAILED)
        self.assertEqual(detail, "log: logs/idx_g0/idx_g0_s1_chunk0.log, exit 3")
        self.state.write_state(self.task, PUBLISH, CANCELLED, error="SIGTERM")
        self.assertEqual(self.status(PUBLISH), (CANCELLED, "SIGTERM"))

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

    def test_lost_says_why_from_the_slurm_log(self):
        with mock.patch.dict(os.environ, {"SLURM_ARRAY_JOB_ID": "18", "SLURM_ARRAY_TASK_ID": "1"}):
            self.state.write_state(self.task, "idx_g0_s1_chunk1", RUNNING)
        self.state.plan["cluster"] = {"output": "logs/slurm/%x_%A_%a.out"}
        slurm = Path(self.paths.build_dir) / "logs" / "slurm"
        slurm.mkdir(parents=True)
        log = slurm / "idx_build_18_1.out"
        (slurm / "idx_build_118_1.out").write_text("*** JOB 118 CANCELLED AT 2026-10-25 ***\n")
        cases = [
            ("", "ended without a status"),  # the log does not say
            ("slurmstepd: error: *** JOB 18 ON n1 CANCELLED AT 2026-10-25T02:17:52 ***\n",
             "job 18_1 was cancelled (scancel), see logs/slurm/idx_build_18_1.out"),
            ("*** JOB 18 ON n1 CANCELLED AT 2026-10-25T02:17:52 DUE TO TIME LIMIT ***\n",
             "reached its time limit"),
            ("slurmstepd: error: Detected 1 oom-kill event(s) in StepId=18.batch\n", "ran out of memory"),
            ("*** JOB 18 ON n1 CANCELLED AT 2026-10-25 DUE TO NODE FAILURE ***\n", "lost its node"),
        ]
        for text, expected in cases:
            with self.subTest(expected):
                log.write_text("kmtricks output\n" * 1000 + text)
                status, detail = self.status("idx_g0_s1_chunk1", alive=lambda job: False)
                self.assertEqual(status, LOST)
                self.assertIn(expected, detail)


class TestAttempts(StatusCase):
    STEP = "idx_g0_s1_chunk1"

    def start(self, job, task_id="0", **fields):
        with mock.patch.dict(os.environ, {"SLURM_ARRAY_JOB_ID": job, "SLURM_ARRAY_TASK_ID": task_id}):
            self.state.write_state(self.task, self.STEP, RUNNING, **fields)

    def test_a_step_started_again_keeps_its_attempts(self):
        self.state.plan["cluster"] = {"output": "logs/slurm/%x_%A_%a.out"}
        slurm = Path(self.paths.build_dir) / "logs" / "slurm"
        slurm.mkdir(parents=True)
        (slurm / "idx_build_18_1.out").write_text("*** JOB 18 ON n1 CANCELLED AT 2026-10-25T02:17:52 ***\n")
        log = str(Path(self.paths.build_dir) / "logs" / "idx_g0" / f"{self.STEP}.log")
        self.start("18", "1", log=log)  # cancelled: no status written
        self.start("19", log=log)
        with mock.patch.dict(os.environ, {"SLURM_ARRAY_JOB_ID": "19", "SLURM_ARRAY_TASK_ID": "0"}):
            self.state.write_state(self.task, self.STEP, FAILED, log=log, error="boom")
        self.start("20", log=log)
        state = self.state.read_state(self.task, self.STEP)
        self.assertEqual(state["job"], "20_0")
        first, second = state["attempts"]
        self.assertEqual((first["job"], first["end"]), ("18_1", "was cancelled (scancel)"))
        self.assertTrue(first["finished"])  # from the SLURM log
        self.assertNotIn("log", first)  # its .prev was replaced by the next attempt
        self.assertEqual((second["job"], second["end"]), ("19_0", "failed: boom"))
        self.assertEqual(second["log"], f"logs/idx_g0/{self.STEP}.log.prev")
        # the end of the step keeps them
        self.state.write_state(self.task, self.STEP, SUCCESS, log=log)
        self.assertEqual(len(self.state.read_state(self.task, self.STEP)["attempts"]), 2)

    def test_attempts_are_shown(self):
        self.start("18", "1")
        self.start("19")
        self.assertIn("attempt 2", self.state.progress()["shards"]["idx_g0"][self.STEP])
        details = step_details(self.state, self.task, {self.STEP})
        self.assertIn("attempt 2", detail_text(details[0], datetime.now()))
        text = render(self.state.progress(), ["idx_g0"], {"idx_g0": details})
        self.assertIn("    attempt 1: job 18_1 @", text)
        self.assertIn("ended without a status", text)
        # a step never started again has no attempt
        self.assertNotIn("attempt", self.state.progress()["shards"]["idx_g0"]["idx_g0_s1_chunk0"])


class TestProgress(StatusCase):
    def test_tree_and_file(self):
        self.complete_run("idx_g0_s1_chunk0")
        self.state.write_state(self.task, "idx_g0_s1_chunk1", FAILED, error="boom")
        sub = Path(self.paths.assets) / "slurm"
        sub.mkdir(parents=True)
        (sub / "submitted.tsv").write_text("idx_g0_publish\t17\nidx_g0_publish\t19\n")

        tree = self.state.write_progress()
        steps = tree["shards"]["idx_g0"]
        self.assertEqual(steps["idx_g0_s1_chunk0"], SUCCESS)
        self.assertEqual(steps["idx_g0_s1_chunk1"], "FAILED (boom)")
        self.assertEqual(steps[PUBLISH], "PENDING (job 19)")  # the last submission
        self.assertEqual(tree["summary"]["failed"], 1)
        self.assertEqual(overall(tree), FAILED)
        on_disk = yaml.safe_load((Path(self.paths.assets) / "progress.yaml").read_text())
        self.assertEqual(on_disk["shards"], tree["shards"])

        text = render(tree)
        self.assertTrue(text.startswith("FAILED: 0/1 shard(s) done, 1 failed"))
        self.assertIn("  publish: PENDING (job 19)", text)
        self.assertNotIn("idx_g0", render(tree, ["other"]).split("\n", 1)[-1])

    def test_done(self):
        self.publish(["s0", "s1"])
        self.assertEqual(overall(self.state.progress()), SUCCESS)

    def test_overall_is_running_while_a_shard_runs(self):
        tree = {"summary": {"shards": 3, "done": 0, "failed": 1, "running": 1, "pending": 1}}
        self.assertEqual(overall(tree), RUNNING)
        tree["summary"].update(running=0)
        self.assertEqual(overall(tree), FAILED)
        tree["summary"].update(failed=0)
        self.assertEqual(overall(tree), PENDING)


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

    def test_line_publish_success_failure(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        publishing = ShardProgress("g", RUNNING, 10, 11, [("publish", now - timedelta(seconds=184))])
        self.assertTrue(shard_line(publishing, 1, now).endswith("publish (3m4s)"))
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
        self.assertEqual(short_step("publish"), "publish")
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


# the tail of a running chunk log, as kmtricks draws its bars
CHUNK_LOG = (
    "Command: bash idx_g0_s1_chunk0.sh\n\n--- STDOUT ---\n"
    "2026-10-24 00:40:34 [idx_g0_s1_chunk0] prepare\n"
    "2026-10-24 00:40:34 [idx_g0_s1_chunk0] build idx_g0_s1_chunk0\n"
    "\nCompute SuperK   [==================================================] [15m:10s] \n"
    "\nCount partitions [===============================>                  ] [03m:12s] \n"
    "\x1b[A\x1b[A\n"
)


class TestDetails(StatusCase):
    def log(self, text):
        path = self.tmp / "chunk0.log"
        path.write_text(text)
        return str(path)

    def running(self, step, log, job="179709_0"):
        started = (datetime.now() - timedelta(minutes=4)).isoformat(timespec="seconds")
        path = Path(self.state.state_path(self.task, step))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"status": RUNNING, "job": job, "node": "node58", "log": log, "started": started}
        ))

    def test_phase_from_the_last_bar_or_marker(self):
        self.assertEqual(kmtricks_phase(self.log(CHUNK_LOG)), [("Count partitions", 62)])
        self.assertEqual(kmtricks_phase(self.log(CHUNK_LOG.split("\nCompute")[0])), [("build", None)])
        done = CHUNK_LOG + "2026-10-24 00:57:37 [idx_g0_s1_chunk0] done\n"
        self.assertEqual(kmtricks_phase(self.log(done)), [("done", None)])
        self.assertIsNone(kmtricks_phase(self.log("")))
        self.assertIsNone(kmtricks_phase(str(self.tmp / "missing.log")))
        self.assertIsNone(kmtricks_phase(""))

    def test_phase_of_the_bars_running_together(self):
        # superk and count run together: their bars are redrawn in turn
        log = self.log(
            "2026-10-24 00:40:34 [idx_g0_s1_chunk0] build idx_g0_s1_chunk0\n"
            "Compute SuperK   [========================>                         ] [00m:12s] \n"
            "Count partitions [==========>                                       ] [00m:12s] \n"
            "\x1b[A\x1b[A\r"
            "Compute SuperK   [========================================>         ] [00m:20s] \n"
            "Count partitions [====================>                             ] [00m:20s] \n"
        )
        self.assertEqual(kmtricks_phase(log), [("Compute SuperK", 80), ("Count partitions", 40)])
        self.assertEqual(
            phase_text(kmtricks_phase(log)), "Compute SuperK 80% · Count partitions 40%"
        )
        # all complete: the last one
        merged = self.log(
            "Count partitions [==================================================] [01m:00s] \n"
            "Merge partitions [==================================================] [00m:30s] \n"
        )
        self.assertEqual(kmtricks_phase(merged), [("Merge partitions", 100)])

    def test_slurm_ram(self):
        def run(cmd, **_):
            out = {"sstat": "576880K\n", "squeue": "19 4G\n"}[cmd[0]]
            return mock.Mock(returncode=0, stdout=out, stderr="")

        status_mod._slurm_job.clear()
        with mock.patch.object(status_mod.subprocess, "run", side_effect=run) as m:
            self.assertEqual(slurm_ram("10_1"), (576880 << 10, 4 << 30))
            slurm_ram("10_1")  # raw id and --mem read once
            self.assertEqual([c.args[0][0] for c in m.call_args_list], ["squeue", "sstat", "sstat"])
            # sstat is asked for the raw id of the array task, not 10_1
            self.assertIn("19.batch", m.call_args_list[1].args[0])
        empty = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(status_mod.subprocess, "run", return_value=empty):
            self.assertIsNone(slurm_ram("10_2"))
        with mock.patch.object(status_mod.subprocess, "run", side_effect=OSError):
            self.assertIsNone(slurm_ram("10_3"))
        self.assertEqual((_rss_bytes("2G"), _rss_bytes("12"), _rss_bytes("?")), (2 << 30, 12 << 10, None))

    def test_ram_text(self):
        self.assertEqual(human_bytes(14.2 * (1 << 30)), "14.2G")
        self.assertEqual(human_bytes(120 << 30), "120G")
        self.assertEqual(ram_text((12 << 30, 100 << 30)), "RAM 12.0G/100G (12%)")
        self.assertEqual(ram_text((589756 << 10, 700 << 30)), "RAM 576M/700G (<1%)")
        self.assertIn("\033[33m", ram_text((85, 100), color=True))
        self.assertIn("\033[31m", ram_text((96, 100), color=True))
        self.assertNotIn("\033", ram_text((10, 100), color=True))
        self.assertEqual(ram_text((512 << 20, None)), "RAM 512M")

    def test_step_details_and_render(self):
        self.complete_run("idx_g0_s1_chunk1")
        self.running("idx_g0_s1_chunk0", self.log(CHUNK_LOG))
        ram = mock.Mock(return_value=(12 << 30, 100 << 30))
        details = step_details(self.state, self.task, ram=ram)
        self.assertEqual([d.status for d in details], [RUNNING, SUCCESS, PENDING])
        running = details[0]
        self.assertEqual((running.job, running.node), ("179709_0", "node58"))
        self.assertEqual(running.phase, [("Count partitions", 62)])
        ram.assert_called_once()
        text = detail_text(running, datetime.now())
        self.assertIn("RUNNING  job 179709_0 @node58  4m", text)
        self.assertIn("RAM 12.0G/100G (12%)  Count partitions 62%", text)
        only = step_details(self.state, self.task, {"idx_g0_s1_chunk1"})
        self.assertEqual([d.step for d in only], ["idx_g0_s1_chunk1"])

        tree = self.state.progress()
        out = render(tree, ["idx_g0"], {"idx_g0": details})
        self.assertIn("  idx_g0_s1_chunk0: RUNNING  job 179709_0 @node58", out)
        self.assertIn("  publish: PENDING", out)
        self.assertNotIn("job", render(tree).split("chunk1")[1])

    def test_failed_step_shows_its_log(self):
        path = Path(self.state.state_path(self.task, "idx_g0_s1_chunk0"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": FAILED, "job": "1_0", "log": "/x.log", "error": "exit 1"}))
        d = step_details(self.state, self.task, {"idx_g0_s1_chunk0"})[0]
        self.assertIn("FAILED  job 1_0", detail_text(d, datetime.now()))
        self.assertIn("exit 1", d.detail)

    def test_display_detailed_sub_lines(self):
        self.running("idx_g0_s1_chunk0", self.log(CHUNK_LOG))
        out = io.StringIO()
        display = ShardDisplay(self.state, live=True, stream=out, detailed=True)
        display.update()
        display.set_ram("idx_g0", "idx_g0_s1_chunk0", 96, 100)
        lines = display.lines()
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[1].startswith("    └ chunk0  job 179709_0 @node58  "), lines[1])
        self.assertIn("\033[31mRAM 96/100 (96%)", lines[1])
        self.assertIn("Count partitions [■■■■■■■", lines[1])
        # not detailed: one line per shard
        plain = ShardDisplay(self.state, live=True, stream=io.StringIO())
        plain.update()
        self.assertEqual(len(plain.lines()), 1)


class TestMonitorLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_stdout_is_written_while_the_command_runs(self):
        log = self.tmp / "run.log"
        samples = []
        script = "echo first; sleep 1.5; echo oops >&2; echo second"
        result = {}

        def run():
            result.update(Wrapper("bash")._monitor_cmd(
                ["bash", "-c", script], log_file=str(log), log_errors_only=False,
                on_sample=samples.append,
            ))

        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.8)
        self.assertIn("first", log.read_text())  # before the end
        t.join()
        text = log.read_text()
        self.assertTrue(text.startswith("Command: bash -c"))
        self.assertLess(text.index("second"), text.index("--- STDERR ---"))
        self.assertLess(text.index("oops"), text.index("--- RESOURCES ---"))
        self.assertEqual(result["return_code"], 0)
        self.assertEqual(result["stdout"], "first\nsecond\n")
        self.assertTrue(samples and all(s > 0 for s in samples))
        info = parse_kmtricks_log(str(log))
        self.assertEqual(info["return_code"], 0)
        self.assertGreater(info["duration_s"], 1)


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
