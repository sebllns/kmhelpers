"""Unit tests for the plan/apply report: kmtricks.log parsing and RunReport."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from pykmhelpers.pipeline.index_ops import ApplyMode, ApplyStatus, IndexOpsConfig
from pykmhelpers.pipeline.index_ops.report import RunReport
from pykmhelpers.pipeline.index_ops.run_log import parse_kmtricks_log
from pykmhelpers.pipeline.index_ops.sizing import BuildParams

# Written by Wrapper._run_cmd for a 16SV4V5 shard (kmtricks 1.4)
KMTRICKS_LOG = """\
Command: kmtricks pipeline --file a.fof --run-dir runs/16SV4V5_g0_initial --kmer-size 25 --nb-partitions 32 --threads 24
Execution time: 1334.79s
Max CPU: 2404.1%
Max Memory: 19087.6836 MB
Return code: 0

--- STDERR ---
[2026-10-19 20:39:58.310] [info] Run with Kmer<32> - uint64_t implementation
[2026-10-19 20:39:58.361] [info] Compute configuration...
[2026-10-19 20:39:58.363] [info] 121 samples found (242 read files).
[2026-10-19 20:40:35.088] [info] Use 32 partitions.
[2026-10-19 20:40:35.134] [info] Use static repartition
[2026-10-19 21:02:05.502] [info] Done in 22m07s - Peak RSS -> 19162.41 MB.
"""


class TestParseKmtricksLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def parse(self, text):
        path = self.tmp / "kmtricks.log"
        path.write_text(text)
        return parse_kmtricks_log(str(path))

    def test_complete_log(self):
        self.assertEqual(
            self.parse(KMTRICKS_LOG),
            {
                "duration_s": 1334.79,
                "max_cpu_pct": 2404.1,
                "return_code": 0,
                "started": "2026-10-19T20:39:58",
                "finished": "2026-10-19T21:02:05",
                "samples": 121,
                "read_files": 242,
                "partitions": 32,
                "peak_rss_mb": 19162.41,
            },
        )

    def test_failed_run_falls_back_to_the_sampled_memory(self):
        text = KMTRICKS_LOG.replace("Return code: 0", "Return code: 1")
        info = self.parse(text.rsplit("\n", 2)[0] + "\n")  # no "Done in" line
        self.assertEqual(info["return_code"], 1)
        self.assertEqual(info["peak_rss_mb"], 19087.6836)
        self.assertEqual(info["finished"], "2026-10-19T20:40:35")

    def test_missing_log(self):
        self.assertEqual(parse_kmtricks_log(str(self.tmp / "none.log")), {})

    def test_unrelated_text(self):
        self.assertEqual(self.parse("nothing here\n"), {})


def make_definition(name="idx_g0_s1", span=3, sample_count=4):
    return SimpleNamespace(
        name=name,
        span=span,
        sample_count=sample_count,
        kmer_size=25,
        abundance_min=2,
        bf_size=27160,
        bitw=1,
        kmer_ratio=1.5,
        get_stored_size=lambda: "1.00KB",
    )


class TestRunReport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = IndexOpsConfig(
            workdir=str(self.tmp), limits='{"ram": 1073741824, "files": 1024}'
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def report(self, mode=ApplyMode.APPLY, dump=True):
        path = str(self.tmp / "report.yaml") if dump else None
        with mock.patch(
            "pykmhelpers.pipeline.index_ops.report.KmindexWrapper"
        ) as wrapper:
            wrapper.return_value.kmindex_version.return_value = "0.7.1"
            wrapper.return_value.which = "/bin/kmindex"
            return RunReport("in.yaml", mode, self.config, path)

    def load(self):
        return yaml.safe_load((self.tmp / "report.yaml").read_text())

    def build_part(self, report, name="idx_g0_s1"):
        i = make_definition(name)
        report.add_span_stats(i.span, i.sample_count, 1000)
        report.record_params(name, i, BuildParams(4, 8, None, 10), 4)
        report.record_runs(
            name,
            {
                name: {
                    "samples": 4,
                    "action": "built",
                    "max_cpu_pct": 200.0,
                    "peak_rss_mb": 512.0,
                }
            },
        )
        report.record(name, ApplyStatus.SUCCESS)

    def test_running_report_then_closed(self):
        report = self.report()
        self.build_part(report)
        report.dump()
        self.assertEqual(self.load()["summary"]["status"], "RUNNING")

        report.record_merge("idx_g0", {"publish": {"mode": "move"}, "disk_bytes": 2048})
        report.fold_merge("idx_g0", ["idx_g0_s1"])
        report.finish()
        report.close()
        data = self.load()

        summary = data["summary"]
        self.assertEqual(summary["command"], "apply")
        self.assertEqual(summary["status"], "SUCCESS")
        self.assertIn("duration_s", summary)
        self.assertEqual(summary["counts"]["SUCCESS"], 1)
        self.assertEqual(summary["totals"]["shards"], 1)
        self.assertEqual(summary["totals"]["runs"], 1)
        self.assertEqual(summary["totals"]["disk_size"], "2.05KB")
        self.assertEqual(summary["spans"][3]["samples"], 4)

        shard = data["shards"]["idx_g0"]
        self.assertEqual(shard["publish"], {"mode": "move"})
        part = shard["idx_g0_s1"]
        self.assertEqual(part["span"], 3)
        self.assertEqual(part["params"]["partitions"], 8)
        run = part["runs"]["idx_g0_s1"]
        self.assertEqual(run["cpu_efficiency"], 0.5)
        self.assertEqual(run["ram_limit_use"], 0.5)
        self.assertEqual(data["limits"]["source"], "--limits")
        self.assertEqual(data["limits"]["files"], 1024)
        self.assertIn("files_soft", data["limits"])
        self.assertIn("files_hard", data["limits"])

    def test_record_keeps_the_details(self):
        report = self.report(dump=False)
        self.build_part(report)
        report.record("idx_g0_s1", ApplyStatus.FAILED, error="boom")
        entry = report.result.details["shards"]["idx_g0_s1"]
        self.assertEqual((entry["result"], entry["error"]), ("FAILED", "boom"))
        self.assertIn("params", entry)

    def test_plan_report(self):
        report = self.report(mode=ApplyMode.PLAN)
        report.close()
        self.assertEqual(self.load()["summary"]["command"], "plan")

    def test_git_commit_only_when_set(self):
        with mock.patch.dict(os.environ, {"GIT_COMMIT": "abc123"}):
            details = self.report(dump=False).result.details
        self.assertEqual(details["kmhelpers"]["git_commit"], "abc123")
        with mock.patch.dict(os.environ, {"GIT_COMMIT": ""}):
            details = self.report(dump=False).result.details
        self.assertNotIn("git_commit", details["kmhelpers"])
        with mock.patch.dict(os.environ):
            os.environ.pop("GIT_COMMIT", None)
            details = self.report(dump=False).result.details
        self.assertNotIn("git_commit", details["kmhelpers"])

    def test_slurm_job(self):
        env = {"SLURM_JOB_ID": "179697", "SLURMD_NODENAME": "node58"}
        with mock.patch.dict(os.environ, env):
            system = self.report(dump=False).result.details["system"]
        self.assertEqual(system["slurm"]["job_id"], "179697")
        self.assertEqual(system["slurm"]["node"], "node58")


if __name__ == "__main__":
    unittest.main()
