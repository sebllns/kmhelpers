"""Unit tests for the automatic group count of ``profile`` (``-g 0``)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from pykmhelpers.core.bloom_filter import SpanManager
from pykmhelpers.core.constants import AUTO_GROUP_MAX
from pykmhelpers.pipeline.span_analyzer import SpanAnalyzer


class TestAutoGroups(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sm = SpanManager(p=0.25, b=1.1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def analyzer(self, counts: dict[int, int]) -> SpanAnalyzer:
        """A baseline of ``{span: sample_count}``, as written by ``profile``."""
        path = self.tmp / "baseline.csv"
        with open(path, "w") as f:
            f.write("span,bf_size,sample_count\n")
            for span, count in sorted(counts.items()):
                f.write(f"{span},{self.sm.get_bf_size(span)},{count}\n")
        return SpanAnalyzer(str(path))

    def test_start_is_one_group_per_samples_per_group(self):
        sa = self.analyzer({100 + 3 * i: 100 for i in range(30)})  # 3000 samples
        self.assertEqual(sa.auto_group_start(), 3)
        # 30 groups wanted, but at most AUTO_GROUP_MAX
        self.assertEqual(sa.auto_group_start(samples_per_group=100), AUTO_GROUP_MAX)
        self.assertEqual(sa.auto_group_start(samples_per_group=5000), 1)

    def test_start_is_within_the_limit(self):
        sa = self.analyzer({100: 400, 160: 400})  # 2 spans
        self.assertEqual(sa.auto_group_limit(), 2)
        self.assertEqual(sa.auto_group_start(samples_per_group=100), 2)
        self.assertEqual(sa.auto_group_start(samples_per_group=100, max_groups=1), 1)

    def test_elbow_adds_groups_beyond_the_start(self):
        """169 samples, 100 small and 69 large: a 2nd group saves 58%, a 3rd 5%."""
        sa = self.analyzer({120: 100, 159: 40, 160: 29})
        self.assertEqual(sa.auto_group_start(), 1)
        self.assertEqual(sa.auto_groups(), 2)

    def test_narrow_distribution_stays_at_the_start(self):
        """Close spans save less than the minimum gain when split."""
        sa = self.analyzer({159: 300, 160: 300})
        self.assertEqual(sa.auto_groups(), 1)

    def test_no_gain_is_enough_returns_the_start(self):
        sa = self.analyzer({100 + 3 * i: 100 for i in range(30)})
        self.assertEqual(sa.auto_groups(min_gain=1.0), sa.auto_group_start())

    def test_bounded_by_max_groups_and_spans(self):
        sa = self.analyzer({100 + 3 * i: 100 for i in range(30)})
        self.assertEqual(sa.auto_group_limit(), min(30, AUTO_GROUP_MAX))
        self.assertLessEqual(sa.auto_groups(min_gain=0.0), sa.auto_group_limit())
        self.assertLessEqual(sa.auto_groups(max_groups=5, min_gain=0.0), 5)


if __name__ == "__main__":
    unittest.main()
