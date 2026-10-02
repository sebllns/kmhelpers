"""Unit tests for the kmtricks build-parameter selection.

Covers the chunk-size decision: the open-files ceiling alone, and the
``max_chunks`` cap that trades threads for bigger chunks.
"""

import math
import unittest

from pykmhelpers.core.build_params import (
    auto_params,
    get_best_params,
    params_for_partitions,
)

KMERS = 10**9
RAM = 32 * 10**9
ULIMIT = 4096
THREADS = 64
SAMPLES = 1000

LIMITS = f'{{"ram": {RAM}, "files": {ULIMIT}, "threads": {THREADS}}}'


def best(**kwargs):
    args = dict(kmers=KMERS, ram=RAM, samples=SAMPLES, ulimit=ULIMIT, n_threads=THREADS)
    args.update(kwargs)
    return get_best_params(**args)


class TestChunkSize(unittest.TestCase):
    def test_no_cap_keeps_the_full_thread_count(self):
        """Baseline: the chunk is the largest that fits all threads in the merge."""
        p = best()
        self.assertEqual(p.samples, ULIMIT // THREADS - 1)
        self.assertEqual(p.threads, THREADS)
        self.assertEqual(math.ceil(SAMPLES / p.samples), 16)

    def test_cap_trades_threads_for_bigger_chunks(self):
        p = best(max_chunks=4)
        self.assertEqual(p.samples, 250)
        self.assertEqual(math.ceil(SAMPLES / p.samples), 4)
        self.assertLessEqual(p.threads, ULIMIT // (p.samples + 1))
        self.assertLessEqual(max(p.files.values()), ULIMIT)

    def test_single_chunk_when_the_cap_is_one(self):
        p = best(max_chunks=1)
        self.assertEqual(p.samples, SAMPLES)
        self.assertLessEqual(max(p.files.values()), ULIMIT)

    def test_cap_already_satisfied_changes_nothing(self):
        self.assertEqual(best(max_chunks=100).samples, best().samples)

    def test_zero_and_none_disable_the_cap(self):
        self.assertEqual(best(max_chunks=0).samples, best().samples)
        self.assertEqual(best(max_chunks=None).samples, best().samples)

    def test_infeasible_cap_warns_and_falls_back(self):
        """A cap the ulimit cannot honour is best effort, not an error."""
        with self.assertLogs("pykmhelpers.core.build_params", "WARNING") as logs:
            p = get_best_params(
                kmers=KMERS, ram=RAM, samples=100, ulimit=8, n_threads=4, max_chunks=1
            )
        self.assertEqual(p.samples, 7)
        self.assertEqual(p.threads, 1)
        self.assertIn("max_chunks=1", logs.output[0])

    def test_chunk_never_exceeds_the_sample_count(self):
        p = best(samples=10, max_chunks=1)
        self.assertEqual(p.samples, 10)


class TestAutoParams(unittest.TestCase):
    def test_cap_is_forwarded(self):
        p = auto_params(kmers=KMERS, samples=SAMPLES, limits=LIMITS, max_chunks=4)
        self.assertEqual(p.samples, 250)
        self.assertLessEqual(max(p.files.values()), ULIMIT)

    def test_no_cap_by_default(self):
        p = auto_params(kmers=KMERS, samples=SAMPLES, limits=LIMITS)
        self.assertEqual(p.samples, ULIMIT // THREADS - 1)


class TestParamsForPartitions(unittest.TestCase):
    def test_cap_applies_at_a_fixed_partition_count(self):
        p = params_for_partitions(
            kmers=KMERS, samples=SAMPLES, partitions=32, limits=LIMITS, max_chunks=4
        )
        self.assertEqual(p.partitions, 32)
        self.assertEqual(p.samples, 250)
        self.assertLessEqual(max(p.files.values()), ULIMIT)

    def test_no_cap_by_default(self):
        p = params_for_partitions(
            kmers=KMERS, samples=SAMPLES, partitions=32, limits=LIMITS
        )
        self.assertEqual(p.samples, ULIMIT // THREADS - 1)


if __name__ == "__main__":
    unittest.main()
