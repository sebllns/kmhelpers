"""Unit tests for pykmhelpers.core.monitor (Linux: /proc sampling)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

from pykmhelpers.cli.kmhelpers import cli
from pykmhelpers.core.monitor import MONITOR_FIELDS, disk_usage, load_monitor, run_monitored

CHILD = """
import sys, time
files = [open(f"{sys.argv[1]}/f{i}", "w") for i in range(6)]
x = bytearray(64 * 2**20)
x[:: 4096] = b"x" * len(x[:: 4096])
with open(f"{sys.argv[1]}/big", "wb") as f:
    f.write(b"0" * 8 * 2**20)
time.sleep(1.0)
sys.exit(3)
"""


class TestRunMonitored(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_monitor_"))
        self.watch = self.tmp / "w"
        self.watch.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_child(self) -> tuple[int, dict]:
        out = str(self.tmp / "m.json")
        code = run_monitored(
            [sys.executable, "-c", CHILD, str(self.watch)], out, [str(self.watch)],
            interval=0.1, disk_interval=0.2, timeline=str(self.tmp / "t.tsv"), label="t",
        )
        return code, json.loads(Path(out).read_text())

    def test_exit_code_time_and_peaks(self):
        code, m = self.run_child()
        self.assertEqual(code, 3)
        self.assertEqual(m["exit_code"], 3)
        self.assertGreaterEqual(m["wall_s"], 1.0)
        self.assertGreaterEqual(m["peak_rss_max_proc_kb"], 60 * 1024)
        self.assertEqual(m["peak_disk_inodes"], 7)
        self.assertGreaterEqual(m["peak_disk_bytes"], 8 * 2**20)
        if os.path.isdir("/proc"):
            self.assertGreaterEqual(m["peak_open_files"], 6 + 3)
            self.assertGreaterEqual(m["peak_rss_tree_kb"], 60 * 1024)
        self.assertGreater(len((self.tmp / "t.tsv").read_text().splitlines()), 3)

    def test_load_monitor(self):
        self.run_child()
        m = load_monitor(str(self.tmp / "m.json"))
        self.assertEqual(set(m), set(MONITOR_FIELDS))
        self.assertIsNone(load_monitor(str(self.tmp / "none.json")))

    def test_disk_usage_missing_dir(self):
        self.assertEqual(disk_usage([str(self.tmp / "missing")]), (0, 0))

    def test_cli(self):
        out = self.tmp / "cli.json"
        r = CliRunner().invoke(
            cli, ["manage", "monitor", "--out", str(out), "--interval", "0.1", "--",
                  sys.executable, "-c", "import sys; sys.exit(2)"],
        )
        self.assertEqual(r.exit_code, 2, r.output)
        self.assertEqual(json.loads(out.read_text())["exit_code"], 2)


if __name__ == "__main__":
    unittest.main()
