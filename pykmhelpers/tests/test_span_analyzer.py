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

    def test_up_to_100_samples_is_one_group(self):
        sa = self.analyzer({100: 50, 140: 50})
        self.assertEqual(sa.auto_group_cap(), 1)
        self.assertEqual(sa.auto_groups(), 1)

    def test_wide_distribution_gets_one_group_per_100_samples(self):
        """169 samples over spans 15x apart in size: a second group pays off."""
        sa = self.analyzer({120: 100, 150: 49, 160: 20})
        self.assertEqual(sa.auto_group_cap(), 2)
        self.assertEqual(sa.auto_groups(), 2)

    def test_narrow_distribution_stays_one_group(self):
        """Close spans save less than 10% when split: one group is enough."""
        sa = self.analyzer({159: 300, 160: 300})
        self.assertEqual(sa.auto_group_cap(), 2)
        self.assertEqual(sa.auto_groups(), 1)

    def test_never_more_groups_than_spans(self):
        sa = self.analyzer({100: 400, 160: 400})
        self.assertEqual(sa.auto_group_cap(), 2)
        self.assertLessEqual(sa.auto_groups(), 2)

    def test_at_most_20_groups(self):
        sa = self.analyzer({100 + 3 * i: 100 for i in range(30)})
        self.assertEqual(sa.auto_group_cap(), AUTO_GROUP_MAX)
        self.assertLessEqual(sa.auto_groups(), AUTO_GROUP_MAX)

    def test_parameters(self):
        sa = self.analyzer({120: 100, 150: 49, 160: 20})
        self.assertEqual(sa.auto_group_cap(samples_per_group=40), 3)
        self.assertEqual(sa.auto_group_cap(samples_per_group=40, max_groups=2), 2)
        # no group saves 100% of the storage
        self.assertEqual(sa.auto_groups(min_gain=1.0), 1)


if __name__ == "__main__":
    unittest.main()
