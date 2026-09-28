"""Unit tests for the index name summarizer used in merge logs."""

import unittest

from pykmhelpers.core.utils import summarize_names


class TestSummarizeNames(unittest.TestCase):
    def chunks(self, prefix, count):
        return [f"{prefix}_chunk{n}" for n in range(count)]

    def test_empty(self):
        self.assertEqual(summarize_names([]), "")

    def test_single_name_is_left_alone(self):
        self.assertEqual(summarize_names(["idx_g0_initial"]), "idx_g0_initial")

    def test_unrelated_names_are_listed(self):
        self.assertEqual(
            summarize_names(["idx_g0_initial", "idx_g1_initial"]),
            "idx_g0_initial, idx_g1_initial",
        )

    def test_chunks_collapse_to_a_range(self):
        self.assertEqual(
            summarize_names(self.chunks("idx_g0_p0_initial", 200)),
            "idx_g0_p0_initial_chunk{0..199}",
        )

    def test_one_chunk_keeps_its_number(self):
        self.assertEqual(
            summarize_names(self.chunks("idx_g0_initial", 1)),
            "idx_g0_initial_chunk0",
        )

    def test_chunks_keep_a_name_that_does_not_belong_to_the_run(self):
        """An update merges the previous version in alongside the chunks."""
        names = self.chunks("idx_g0_initial", 50) + ["idx_g0_prev_20260927_120000"]
        self.assertEqual(
            summarize_names(names),
            "idx_g0_initial_chunk{0..49}, idx_g0_prev_20260927_120000",
        )

    def test_a_gap_in_the_run_is_counted(self):
        self.assertEqual(
            summarize_names(["a_chunk0", "a_chunk2", "a_chunk5", "a_chunk9"]),
            "a_chunk{0..9} (4)",
        )

    def test_several_runs_are_kept_apart(self):
        names = self.chunks("idx_g0_initial", 10) + self.chunks("idx_g1_initial", 10)
        self.assertEqual(
            summarize_names(names),
            "idx_g0_initial_chunk{0..9}, idx_g1_initial_chunk{0..9}",
        )

    def test_too_many_groups_are_truncated(self):
        names = [f"part_{n}_x" for n in range(10)]
        summary = summarize_names(names, max_groups=2)
        self.assertEqual(summary, "part_0_x, part_1_x, ... (10 in total)")

    def test_names_without_a_number_are_untouched(self):
        self.assertEqual(summarize_names(["alpha", "beta"]), "alpha, beta")


if __name__ == "__main__":
    unittest.main()
