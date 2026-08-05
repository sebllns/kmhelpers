"""Unit tests for the `kmhelpers results` CLI command.

Uses click's CliRunner (in-process) rather than a subprocess, unlike
test_pipeline_e2e.py: `results` is read-only and touches no process-global
registry (e.g. IndexDB), so running several invocations in one process is safe.
"""

import json
import unittest
from pathlib import Path

from click.testing import CliRunner

from pykmhelpers.cli.results import results
from pykmhelpers.tests.test_query_result import write_result_file


class ResultsCliBase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self._tmp_ctx = self.runner.isolated_filesystem()
        self.tmp = self._tmp_ctx.__enter__()
        self.addCleanup(self._tmp_ctx.__exit__, None, None, None)

    def write_run(self, rel_dir, samples, index="idx_0", query="q0"):
        write_result_file(
            self.tmp,
            f"{rel_dir}/q0/kmindex_output",
            "a.jsonl",
            [{"index": index, "query": query, "samples": samples}],
        )


class TestCheckMode(ResultsCliBase):
    def test_check_passes_above_min_score(self):
        self.write_run("results", {"s0": 0.95})
        result = self.runner.invoke(
            results, ["results", "--check", "s0", "--min-score", "0.9"]
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output.strip(), "OK: s0 scored 0.950 in results")

    def test_check_fails_below_min_score(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(
            results, ["results", "--check", "s0", "--min-score", "0.9"]
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("FAIL: s0 scored 0.5 (< 0.9) in results", result.output)

    def test_check_fails_when_sample_absent(self):
        self.write_run("results", {"s0": 0.95})
        result = self.runner.invoke(
            results, ["results", "--check", "missing", "--min-score", "0.9"]
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("FAIL: missing scored 0", result.output)

    def test_check_fails_when_no_jsonl_found(self):
        Path(self.tmp, "empty").mkdir()
        result = self.runner.invoke(
            results, ["empty", "--check", "s0", "--min-score", "0.9"]
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("FAIL: no kmindex_output/*.jsonl under empty", result.output)

    def test_check_merges_multiple_dirs(self):
        self.write_run("run1", {"s0": 0.5})
        self.write_run("run2", {"s0": 0.95})
        result = self.runner.invoke(
            results, ["run1", "run2", "--check", "s0", "--min-score", "0.9"]
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("in run1, run2", result.output)

    def test_default_min_score(self):
        self.write_run("results", {"s0": 0.8})
        result = self.runner.invoke(results, ["results", "--check", "s0"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("< 0.9", result.output)


class TestConvertMode(ResultsCliBase):
    def test_no_jsonl_found_is_a_click_error(self):
        Path(self.tmp, "empty").mkdir()
        result = self.runner.invoke(results, ["empty"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("no kmindex_output/*.jsonl under empty", result.output)

    def test_default_format_is_tsv(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(results, ["results"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("seq\ts0", result.output)

    def test_json_format_is_valid_json(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(results, ["results", "-f", "json"])
        self.assertEqual(result.exit_code, 0)
        parsed = json.loads(result.output)
        self.assertIn("idx_0", parsed)

    def test_html_format(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(results, ["results", "-f", "html"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("<html", result.output)

    def test_md_format(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(results, ["results", "-f", "md"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Sequence \\ Sample", result.output)

    def test_yaml_format(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(results, ["results", "-f", "yaml"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("idx_0:", result.output)

    def test_output_writes_to_file(self):
        self.write_run("results", {"s0": 0.5})
        result = self.runner.invoke(
            results, ["results", "-f", "json", "-o", "out.json"]
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "")
        parsed = json.loads(Path(self.tmp, "out.json").read_text())
        self.assertIn("idx_0", parsed)

    def test_nonexistent_dir_is_usage_error(self):
        result = self.runner.invoke(results, ["does_not_exist"])
        self.assertEqual(result.exit_code, 2)


if __name__ == "__main__":
    unittest.main()
