import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import click
import yaml
from click.testing import CliRunner

from pykmhelpers.core import run_record as rr
from pykmhelpers.core.run_record import (
    HISTORY_FILE,
    CommandLog,
    append_history,
    run_record,
    step_of,
)


def tool(seen: list):
    """A command with an argument, options, flags and a one-shot flag; it
    records its ``run`` block in ``seen``."""

    @click.command(name="tool")
    @click.argument("inputs", nargs=-1)
    @click.option("-o", "--output", "output")
    @click.option("--sb", "--shard-budget", "shard_budget", default="2**43")
    @click.option("--fast/--no-fast", default=True)
    @click.option("--tag", multiple=True)
    @click.option("--replan", is_flag=True)
    @click.pass_context
    def cmd(ctx, inputs, output, shard_budget, fast, tag, replan):
        seen.append(run_record(ctx))

    return cmd


class TestRunRecord(unittest.TestCase):
    def run_tool(self, args, argv=None):
        seen: list = []
        with mock.patch.object(rr.sys, "argv", ["/x/bin/kmhelpers", *(argv or [])]):
            result = CliRunner().invoke(tool(seen), args)
        self.assertEqual(result.exit_code, 0, result.output)
        return seen[0]

    def test_given_options_make_the_step(self):
        run = self.run_tool(["a.fa", "b.fa", "-o", "out", "--sb", "2**34", "--no-fast", "--replan"])
        self.assertEqual(
            run["step"],
            [{"tool": {"inputs": ["a.fa", "b.fa"], "output": "out", "shard_budget": "2**34", "fast": False}}],
        )
        # --replan (given) is not replayed; the defaults are kept apart
        self.assertEqual(run["defaults"], {"tag": []})
        self.assertNotIn("replan", run["step"][0]["tool"])
        self.assertEqual(run["cwd"], os.getcwd())

    def test_command_line_as_typed(self):
        argv = ["tool", "a.fa", "--sb", "2**34"]
        run = self.run_tool(argv[1:], argv=argv)
        self.assertEqual(run["command"], "kmhelpers tool a.fa --sb '2**34'")

    def test_command_run_by_a_pipeline_has_no_step(self):
        """The pipeline file is the record of the commands it runs."""
        seen: list = []
        cmd = tool(seen)

        @click.group()
        def root():
            pass

        @root.command(name="pipeline")
        @click.argument("pipeline_file")
        @click.pass_context
        def pipeline(ctx, pipeline_file):
            ctx.invoke(cmd, output="o", inputs=("a.fa",))

        argv = ["pipeline", "p.yaml"]
        with mock.patch.object(rr.sys, "argv", ["kmhelpers", *argv]):
            result = CliRunner().invoke(root, argv)
        self.assertEqual(result.exit_code, 0, result.output)
        run = seen[0]
        self.assertEqual(run["command"], "kmhelpers pipeline p.yaml")
        self.assertEqual((run["via"], run["pipeline"]), ("pipeline", os.path.abspath("p.yaml")))
        self.assertNotIn("step", run)
        self.assertNotIn("defaults", run)
        self.assertIsNone(step_of({"run": run}))

    def test_global_options(self):
        seen: list = []

        @click.group()
        @click.option("-Y", "--yes", is_flag=True)
        @click.option("-V", "--verbose", count=True)
        @click.option("-q", "--quiet", count=True)
        def root(yes, verbose, quiet):
            pass

        root.add_command(tool(seen))
        result = CliRunner().invoke(root, ["-Y", "-V", "-V", "tool", "a.fa"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(seen[0]["globals"], {"yes": True, "verbose": 2})
        self.assertNotIn("globals", self.run_tool(["a.fa"]))

    def test_no_command_no_record(self):
        self.assertIsNone(run_record())

    def test_step_of(self):
        self.assertEqual(step_of({"run": {"step": [{"design": {}}]}}), [{"design": {}}])
        self.assertIsNone(step_of({"design": {"output_dir": "x"}}))
        self.assertIsNone(step_of([{"apply": {}}]))


class TestCommandLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_report_and_history(self):
        logs = self.tmp / "logs"
        log = CommandLog(str(logs), "design")
        log.begin("list")
        log.step("list", "SUCCESS", output="x.jsonl")
        report = yaml.safe_load(Path(log.path).read_text())
        self.assertEqual(report["summary"]["status"], "RUNNING")  # written as it goes
        log.close("SUCCESS", samples=3)
        report = yaml.safe_load(Path(log.path).read_text())
        self.assertEqual(report["summary"]["status"], "SUCCESS")
        self.assertEqual(report["summary"]["samples"], 3)
        self.assertEqual(report["steps"]["list"]["output"], "x.jsonl")
        self.assertIn("commit", report["run"]["kmhelpers"])
        lines = (logs / HISTORY_FILE).read_text().splitlines()
        self.assertEqual(lines[0].split("\t"), ["time", "report", "status", "duration_s", "command"])
        self.assertEqual(lines[1].split("\t")[1:3], ["design", "SUCCESS"])

    def test_failure_goes_to_the_step_under_way(self):
        log = CommandLog(str(self.tmp / "logs"), "design")
        log.begin("profile")
        log.close("FAILED", "FAILED ('profile'): no sample")
        report = yaml.safe_load(Path(log.path).read_text())
        self.assertEqual(report["steps"]["profile"]["status"], "FAILED")
        self.assertEqual(report["steps"]["profile"]["error"], "FAILED ('profile'): no sample")
        self.assertEqual(report["summary"]["error"], "FAILED ('profile'): no sample")

    def test_history_appends(self):
        for status in ("FAILED", "SUCCESS"):
            append_history(str(self.tmp), "apply", status, 1.25, "kmhelpers apply db -o b")
        lines = (self.tmp / HISTORY_FILE).read_text().splitlines()
        self.assertEqual(len(lines), 3)  # one header
        self.assertEqual(lines[2].split("\t")[1:], ["apply", "SUCCESS", "1.2", "kmhelpers apply db -o b"])


if __name__ == "__main__":
    unittest.main()
