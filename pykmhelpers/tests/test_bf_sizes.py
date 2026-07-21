"""Unit tests for SpanManager and Bloom filter sizing helpers.

Covers the v0.6.3 changes to ``pykmhelpers.core.bloom_filter``: the ``b`` base
parameter on ``SpanManager``, the ``min_kmer_count``/``max_kmer_count`` helpers,
the module-level matrix cost functions, and ``BloomFilterSpecs.matrix_size``.
"""

import unittest

from pykmhelpers.core.bloom_filter import (
    BloomFilterSpecs,
    SpanManager,
    kmindex_matrix_bit_count,
    kmindex_matrix_storage_cost,
)

# Golden bf_size values for the default SpanManager (p=0.25, b=2.0), spans 1-36.
# These lock the current behaviour; regenerate only if the sizing formula changes.
EXPECTED_BF_SIZES = {
    1: 16,
    2: 24,
    3: 48,
    4: 96,
    5: 184,
    6: 376,
    7: 744,
    8: 1480,
    9: 2960,
    10: 5912,
    11: 11824,
    12: 23640,
    13: 47280,
    14: 94552,
    15: 189096,
    16: 378200,
    17: 756392,
    18: 1512776,
    19: 3025552,
    20: 6051104,
    21: 12102208,
    22: 24204408,
    23: 48408816,
    24: 96817632,
    25: 193635256,
    26: 387270504,
    27: 774541008,
    28: 1549082008,
    29: 3098164016,
    30: 6196328024,
    31: 12392656040,
    32: 24785312080,
    33: 49570624152,
    34: 99141248304,
    35: 198282496600,
    36: 396564993200,
}


class TestSpanManagerBfSize(unittest.TestCase):
    """Tests for SpanManager.get_bf_size."""

    def setUp(self):
        self.sm = SpanManager(p=0.25)

    def test_bf_size_golden_values(self):
        """bf_size for spans 1-36 matches the locked golden values."""
        for span, expected in EXPECTED_BF_SIZES.items():
            self.assertEqual(self.sm.get_bf_size(span), expected, msg=f"span={span}")

    def test_bf_size_is_byte_aligned(self):
        """Every bf_size is a whole number of bytes (multiple of 8 bits)."""
        for span in range(1, 37):
            self.assertEqual(self.sm.get_bf_size(span) % 8, 0, msg=f"span={span}")

    def test_bf_size_monotonic(self):
        """bf_size strictly increases with span."""
        sizes = [self.sm.get_bf_size(s) for s in range(1, 37)]
        for prev, cur in zip(sizes, sizes[1:]):
            self.assertLess(prev, cur)

    def test_base_parameter_changes_result(self):
        """A different base b yields a different bf_size."""
        self.assertNotEqual(
            SpanManager(b=2.0).get_bf_size(5),
            SpanManager(b=3.0).get_bf_size(5),
        )


class TestSpanManagerDispatch(unittest.TestCase):
    """Tests for dispatch / min_kmer_count / max_kmer_count round-trips."""

    def setUp(self):
        self.sm = SpanManager(p=0.25)

    def test_min_max_kmer_count_ordering(self):
        """min_kmer_count(s) <= max_kmer_count(s) < min_kmer_count(s+1)."""
        for span in range(1, 20):
            self.assertLessEqual(
                self.sm.min_kmer_count(span), self.sm.max_kmer_count(span)
            )
            self.assertLess(
                self.sm.max_kmer_count(span), self.sm.min_kmer_count(span + 1)
            )

    def test_dispatch_round_trip(self):
        """dispatch maps both ends of a span's k-mer range back to that span."""
        for span in range(1, 20):
            self.assertEqual(self.sm.dispatch(self.sm.min_kmer_count(span)), span)
            self.assertEqual(self.sm.dispatch(self.sm.max_kmer_count(span)), span)

    def test_min_kmer_count_tracks_base(self):
        """min_kmer_count follows the configured base b."""
        self.assertEqual(SpanManager(b=2.0).min_kmer_count(5), 32)
        self.assertEqual(SpanManager(b=3.0).min_kmer_count(5), 243)


class TestSpanManagerGuards(unittest.TestCase):
    """Tests for constructor and argument constraints."""

    def test_rejects_non_positive_p(self):
        with self.assertRaises(AssertionError):
            SpanManager(p=0)

    def test_rejects_non_positive_b(self):
        with self.assertRaises(AssertionError):
            SpanManager(b=0)

    def test_dispatch_rejects_non_positive_count(self):
        with self.assertRaises(AssertionError):
            SpanManager().dispatch(0)


class TestMatrixHelpers(unittest.TestCase):
    """Tests for the module-level matrix cost helpers and BloomFilterSpecs."""

    def test_matrix_bit_count(self):
        self.assertEqual(kmindex_matrix_bit_count(100, 10), 1000)

    def test_matrix_storage_cost_byte_alignment(self):
        # cols padded to whole bytes: ceil(10/8) = 2 bytes;
        # rows padded to a multiple of 64: 100 -> 128; 2 * 128 = 256.
        self.assertEqual(kmindex_matrix_storage_cost(100, 10), 256)

    def test_bloomfilterspecs_matrix_size(self):
        specs = BloomFilterSpecs(100, 10, 1)
        self.assertEqual(specs.matrix_size, 100 * 10)


class TestBloomFilterSpecsByteCounts(unittest.TestCase):
    """Tests for BloomFilterSpecs byte-count math (column_byte_count refactored in 0.6.3)."""

    def setUp(self):
        # rows=128, cols=16, parts=1
        self.specs = BloomFilterSpecs(128, 16, 1)

    def test_matrix_size(self):
        self.assertEqual(self.specs.matrix_size, 128 * 16)

    def test_row_byte_count(self):
        # cols padded to whole bytes: ceil(16/8) = 2
        self.assertEqual(self.specs.row_byte_count(), 2)

    def test_column_byte_count(self):
        # rows padded to a multiple of 64: 128 -> 128
        self.assertEqual(self.specs.column_byte_count(), 128)

    def test_total_byte_count(self):
        self.assertEqual(self.specs.total_byte_count(), 2 * 128)

    def test_column_byte_count_accounts_for_partitions(self):
        # rows/parts padded per partition: ceil(64/64)*64*2 = 128
        parted = BloomFilterSpecs(128, 16, 2)
        self.assertEqual(parted.column_byte_count(), 128)
        self.assertEqual(parted.total_byte_count(), 256)


if __name__ == "__main__":
    unittest.main()
