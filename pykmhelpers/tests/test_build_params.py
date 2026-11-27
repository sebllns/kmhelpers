"""Unit tests for the kmtricks build-parameter selection.

Covers the chunk-size decision: the open-files ceiling alone, and the
``max_chunks`` cap that trades merge tasks for bigger chunks. The merge stage
opens ``min(T, P) * (S + 1)`` files (kmtricks_tacc_benchmarks E1).
"""

import math
import unittest

from pykmhelpers.core.build_params import (
    auto_params,
    get_best_params,
    merge_stage_ram,
    params_for_partitions,
    ram_chunk,
)

KMERS = 10**9
RAM = 32 * 10**9
ULIMIT = 4096
THREADS = 64
SAMPLES = 1000

LIMITS = f'{{"ram": {RAM}, "files": {ULIMIT}, "threads": {THREADS}}}'

# RAM-minimum partitions at THREADS: ceil(KMERS * 8 * 1.05 * 64 / RAM) = 17
PARTS = 17


def merge_files(p):
    return min(p.threads, p.partitions) * (p.samples + 1)


def best(**kwargs):
    args = dict(kmers=KMERS, ram=RAM, samples=SAMPLES, ulimit=ULIMIT, n_threads=THREADS)
    args.update(kwargs)
    return get_best_params(**args)


class TestChunkSize(unittest.TestCase):
    def test_no_cap_keeps_the_full_thread_count(self):
        """Baseline: the chunk is the largest that fits min(T, P) merge tasks."""
        p = best()
        self.assertEqual(p.partitions, PARTS)
        self.assertEqual(p.samples, ULIMIT // PARTS - 1)
        self.assertEqual(p.threads, THREADS)
        self.assertEqual(math.ceil(SAMPLES / p.samples), 5)
        self.assertEqual(p.files["merge"], merge_files(p))
        self.assertLessEqual(max(p.files.values()), ULIMIT)

    def test_merge_files_follow_the_merge_tasks_not_the_threads(self):
        """At T > P the merge holds P * (S + 1) files, not T * (S + 1)."""
        p = best()
        self.assertGreater(p.threads, p.partitions)
        self.assertEqual(p.files["merge"], p.partitions * (p.samples + 1))

    def test_threads_below_partitions_bound_the_chunk(self):
        """With T < P the merge tasks are the threads."""
        p = best(ram=RAM // 8, n_threads=8)
        self.assertLess(p.threads, p.partitions)
        self.assertEqual(p.samples, ULIMIT // 8 - 1)
        self.assertEqual(p.files["merge"], p.threads * (p.samples + 1))

    def test_cap_trades_threads_for_bigger_chunks(self):
        p = best(max_chunks=4)
        self.assertEqual(p.samples, 250)
        self.assertEqual(math.ceil(SAMPLES / p.samples), 4)
        self.assertLessEqual(merge_files(p), ULIMIT)
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
        # one partition, so one merge task: 3 threads still fit 1 * (7 + 1) files
        self.assertEqual(p.partitions, 1)
        self.assertEqual(p.threads, 3)
        self.assertIn("max_chunks=1", logs.output[0])

    def test_chunk_never_exceeds_the_sample_count(self):
        p = best(samples=10, max_chunks=1)
        self.assertEqual(p.samples, 10)

    def test_chunk_model_caps_the_chunk(self):
        p = best(max_chunk_samples=40)
        self.assertEqual(p.samples, 40)
        self.assertEqual(p.threads, THREADS)

    def test_chunk_model_bounds_max_chunks(self):
        """max_chunks raises the chunk up to the chunk budget, not beyond."""
        self.assertEqual(best(max_chunks=4, max_chunk_samples=500).samples, 250)
        with self.assertLogs("pykmhelpers.core.build_params", "WARNING"):
            p = best(max_chunks=4, max_chunk_samples=200)
        self.assertEqual(p.samples, 200)
        self.assertEqual(math.ceil(SAMPLES / p.samples), 5)

    def test_chunk_model_above_the_optimum_changes_nothing(self):
        self.assertEqual(best(max_chunk_samples=10**6).samples, best().samples)


class TestAutoParams(unittest.TestCase):
    def test_cap_is_forwarded(self):
        p = auto_params(kmers=KMERS, samples=SAMPLES, limits=LIMITS, max_chunks=4)
        self.assertEqual(p.samples, 250)
        self.assertLessEqual(max(p.files.values()), ULIMIT)

    def test_no_cap_by_default(self):
        p = auto_params(kmers=KMERS, samples=SAMPLES, limits=LIMITS)
        self.assertEqual(p.samples, ULIMIT // PARTS - 1)


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
        self.assertEqual(p.samples, ULIMIT // 32 - 1)
        self.assertEqual(p.threads, THREADS)
        self.assertEqual(p.files["merge"], 32 * (p.samples + 1))

    def test_warns_when_one_thread_exceeds_ram(self):
        limits = '{"ram": 1000, "files": 4096, "threads": 4}'
        with self.assertLogs("pykmhelpers.core.build_params", "WARNING"):
            p = params_for_partitions(
                kmers=KMERS, samples=SAMPLES, partitions=4, limits=limits
            )
        self.assertEqual(p.threads, 1)


if __name__ == "__main__":
    unittest.main()


class TestMergeStageRam(unittest.TestCase):
    """The merge stage holds 0.07 GiB + 169 KiB per open sample and task (E2)."""

    # 10**7 k-mers: the count stage fits 64 threads, the merge stage binds
    RAM = 200 * 10**6
    LIMITS = f'{{"ram": {RAM}, "files": {ULIMIT}, "threads": {THREADS}}}'

    def fixed(self, **kwargs):
        return params_for_partitions(
            kmers=10**7, samples=SAMPLES, partitions=32, limits=self.LIMITS, **kwargs
        )

    def test_ram_binds_the_chunk(self):
        p = self.fixed()
        self.assertEqual(p.threads, THREADS)
        self.assertEqual(p.samples, ram_chunk(self.RAM, 32))
        self.assertLess(p.samples, ULIMIT // 32 - 1)
        self.assertLessEqual(merge_stage_ram(32, p.samples), self.RAM)

    def test_cap_lowers_the_threads_to_fit_ram(self):
        """250 samples per chunk fit 16 merge tasks in files, 2 in RAM."""
        p = self.fixed(max_chunks=4)
        self.assertEqual(p.samples, 250)
        self.assertEqual(p.threads, 2)
        self.assertLessEqual(merge_stage_ram(p.threads, p.samples), self.RAM)

    def test_large_ram_keeps_the_files_bound(self):
        p = best()
        self.assertEqual(p.samples, ULIMIT // PARTS - 1)
        self.assertLess(p.samples, ram_chunk(RAM, PARTS))
