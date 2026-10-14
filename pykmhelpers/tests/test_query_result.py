"""Unit tests for KmindexQueryResult, plain jsonl and jsonl_vec input.

kmindex writes one record per line, either
``{"index":..,"query":..,"samples":{"s":0.69}}`` (jsonl) or
``{"index":..,"query":..,"samples":{"s":{"P":[0/1,..],"R":0.69}}}`` (jsonl_vec).
Both must yield the same score matrix, the vec form additionally keeping the
per-k-mer presence vector.
"""

import json
import tempfile
import unittest
from pathlib import Path

from pykmhelpers.pipeline.query import KmindexQueryResult

VECTOR = [1] * 6 + [0] * 2 + [1] * 3 + [0] + [1] * 8
RATIO = sum(VECTOR) / len(VECTOR)


def write_jsonl(directory, name, records):
    path = Path(directory) / name
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return str(path)


class QueryResultBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def plain_file(self, score=RATIO):
        return write_jsonl(
            self.tmp,
            "plain.jsonl",
            [{"index": "idx_0", "query": "q0", "samples": {"s0": score}}],
        )

    def vec_file(self, vector=VECTOR, ratio=RATIO, with_r=True):
        sample = {"P": vector}
        if with_r:
            sample["R"] = ratio
        return write_jsonl(
            self.tmp,
            "vec.jsonl",
            [{"index": "idx_0", "query": "q0", "samples": {"s0": sample}}],
        )


class TestLoad(QueryResultBase):
    def test_plain_jsonl(self):
        r = KmindexQueryResult(self.plain_file())
        self.assertEqual(r.items, {"idx_0": {"q0": {"s0": RATIO}}})
        self.assertFalse(r.has_vectors)

    def test_vec_jsonl(self):
        r = KmindexQueryResult(self.vec_file())
        self.assertEqual(r.items, {"idx_0": {"q0": {"s0": RATIO}}})
        self.assertTrue(r.has_vectors)
        self.assertEqual(r.vectors["idx_0"]["q0"]["s0"], VECTOR)

    def test_vec_without_ratio_is_recomputed(self):
        r = KmindexQueryResult(self.vec_file(with_r=False))
        self.assertAlmostEqual(r.items["idx_0"]["q0"]["s0"], RATIO)

    def test_vec_equals_plain(self):
        self.assertEqual(
            KmindexQueryResult(self.vec_file()), KmindexQueryResult(self.plain_file())
        )

    def test_empty_samples_ignored(self):
        path = write_jsonl(
            self.tmp, "empty.jsonl", [{"index": "i", "query": "q", "samples": {}}]
        )
        self.assertEqual(KmindexQueryResult(path).items, {})

    def test_unsupported_sample_skipped(self):
        path = write_jsonl(
            self.tmp,
            "bad.jsonl",
            [{"index": "i", "query": "q", "samples": {"s0": "oops", "s1": 0.5}}],
        )
        self.assertEqual(KmindexQueryResult(path).items, {"i": {"q": {"s1": 0.5}}})

    def test_max_score(self):
        r = KmindexQueryResult(self.vec_file())
        self.assertAlmostEqual(r.max_score("s0"), RATIO)
        self.assertEqual(r.max_score("absent"), 0)

    def test_get_index_result_keeps_vectors(self):
        r = KmindexQueryResult(self.vec_file()).get_index_result("idx_0")
        self.assertEqual(r.vectors["idx_0"]["q0"]["s0"], VECTOR)
        self.assertEqual(KmindexQueryResult(self.vec_file()).get_index_result("x").items, {})


class TestVectorHelpers(unittest.TestCase):
    def test_stats(self):
        stats = KmindexQueryResult._vector_stats(VECTOR)
        self.assertEqual(stats["n_kmers"], 20)
        self.assertEqual(stats["covered"], 17)
        self.assertEqual(stats["longest_run"], 8)
        self.assertEqual(stats["gaps"], 2)
        self.assertAlmostEqual(stats["ratio"], RATIO)

    def test_stats_empty(self):
        self.assertEqual(
            KmindexQueryResult._vector_stats([]),
            {"n_kmers": 0, "covered": 0, "ratio": 0.0, "longest_run": 0, "gaps": 0},
        )

    def test_stats_leading_gap(self):
        stats = KmindexQueryResult._vector_stats([0, 0, 1, 1])
        self.assertEqual(stats["gaps"], 1)
        self.assertEqual(stats["longest_run"], 2)

    def test_rle(self):
        self.assertEqual(
            KmindexQueryResult._rle(VECTOR),
            [[1, 6], [0, 2], [1, 3], [0, 1], [1, 8]],
        )

    def test_rle_starting_with_a_gap(self):
        self.assertEqual(KmindexQueryResult._rle([0, 0, 1]), [[0, 2], [1, 1]])

    def test_rle_empty(self):
        self.assertEqual(KmindexQueryResult._rle([]), [])

    def test_rle_round_trip(self):
        decoded = []
        for value, count in KmindexQueryResult._rle(VECTOR):
            decoded.extend([value] * count)
        self.assertEqual(decoded, VECTOR)


class TestConverters(QueryResultBase):
    def test_all_formats_on_vec_input(self):
        r = KmindexQueryResult(self.vec_file())
        for fmt in ("md", "html", "tsv", "json", "yaml"):
            with self.subTest(fmt=fmt):
                self.assertTrue(r.convert(fmt, threshold=0.0))

    def test_plain_output_unchanged_by_vec_support(self):
        plain = KmindexQueryResult(self.plain_file())
        self.assertEqual(
            json.loads(plain.generate_json(0.0)), {"idx_0": {"s0": {"q0": RATIO}}}
        )
        self.assertNotIn("Coverage", plain.generate_markdown(0.0))
        # The track CSS is static, only the coverage section must be absent
        html = plain.generate_html(0.0)
        self.assertNotIn("<h2>Coverage</h2>", html)
        self.assertNotIn("class='track'", html)

    def test_coverage_tsv(self):
        lines = (
            KmindexQueryResult(self.vec_file()).generate_coverage_tsv(0.0).split("\n")
        )
        self.assertEqual(
            lines[0],
            "query\tsample\tindex\tR\tn_kmers\tcovered\tlongest_run\tgaps\truns",
        )
        self.assertEqual(
            lines[1],
            f"q0\ts0\tidx_0\t{RATIO:.3f}\t20\t17\t8\t2\t[[1,6],[0,2],[1,3],[0,1],[1,8]]",
        )

    def test_coverage_tsv_respects_threshold(self):
        r = KmindexQueryResult(self.vec_file())
        self.assertEqual(len(r.generate_coverage_tsv(0.99).split("\n")), 1)

    def test_score_matrix_tsv_has_no_coverage(self):
        tsv = KmindexQueryResult(self.vec_file()).generate_tsv(0.0)
        self.assertEqual(tsv, f"seq\ts0\nq0\t{RATIO:.3f}")

    def test_markdown_coverage_table(self):
        md = KmindexQueryResult(self.vec_file()).generate_markdown(0.0)
        self.assertIn("## Coverage", md)
        self.assertIn("longest_run", md)

    def test_html_coverage_track(self):
        html = KmindexQueryResult(self.vec_file()).generate_html(0.0)
        self.assertIn("<h2>Coverage</h2>", html)
        self.assertIn("class='track'", html)
        # One bucket per k-mer while the vector is shorter than _TRACK_BUCKETS
        self.assertEqual(html.count("title='"), len(VECTOR))

    def test_json_carries_rle_vector(self):
        entry = json.loads(KmindexQueryResult(self.vec_file()).generate_json(0.0))
        entry = entry["idx_0"]["s0"]["q0"]
        self.assertAlmostEqual(entry["R"], RATIO)
        self.assertEqual(entry["covered"], 17)
        self.assertEqual(entry["P"], [[1, 6], [0, 2], [1, 3], [0, 1], [1, 8]])

    def test_yaml_has_stats_and_inline_vector(self):
        text = KmindexQueryResult(self.vec_file()).generate_yaml(0.0)
        self.assertIn("longest_run: 8", text)
        self.assertIn("P: [[1, 6], [0, 2], [1, 3], [0, 1], [1, 8]]", text)

    def test_yaml_plain_input_has_no_stats(self):
        text = KmindexQueryResult(self.plain_file()).generate_yaml(0.0)
        self.assertEqual(text.strip(), f"idx_0:\n  s0:\n    q0: {round(RATIO, 3)}")

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            KmindexQueryResult(self.plain_file()).convert("xml")


class TestMatchStats(unittest.TestCase):
    # q0 hits s0 (perfect) and s1 in g0, s2 in g1; q1 hits s1 in g0 only
    ITEMS = {
        "g0": {"q0": {"s0": 1.0, "s1": 0.4}, "q1": {"s1": 0.6, "s3": 0.01}},
        "g1": {"q0": {"s2": 0.2}},
    }

    def stats(self, sizes=None, threshold=0.05):
        r = KmindexQueryResult(items=self.ITEMS, index_sizes=sizes)
        return {(row["query"], row["index"]): row for row in r.match_stats(threshold)}

    def test_per_query(self):
        rows = self.stats({"g0": 4, "g1": 2})
        q0 = rows[("q0", "g0")]
        self.assertEqual((q0["matched"], q0["perfect"]), (2, 1))
        self.assertAlmostEqual(q0["matched_pct"], 50.0)
        self.assertAlmostEqual(q0["mean"], 0.7)
        q0_all = rows[("q0", "all")]
        self.assertEqual((q0_all["samples"], q0_all["matched"]), (6, 3))
        self.assertAlmostEqual(q0_all["median"], 0.4)
        # s3 is below threshold, q1 has no row for g1
        self.assertEqual(rows[("q1", "g0")]["matched"], 1)
        self.assertNotIn(("q1", "g1"), rows)

    def test_overall_best_score_per_sample(self):
        rows = self.stats({"g0": 4, "g1": 2})
        g0 = rows[("*", "g0")]
        # s1 counted once with its best score 0.6
        self.assertEqual((g0["matched"], g0["perfect"]), (2, 1))
        self.assertAlmostEqual(g0["mean"], 0.8)
        overall = rows[("*", "all")]
        self.assertEqual((overall["samples"], overall["matched"]), (6, 3))
        self.assertAlmostEqual(overall["matched_pct"], 50.0)

    def test_subindex_without_match_listed(self):
        rows = self.stats({"g0": 4, "g1": 2, "g2": 10})
        self.assertEqual(rows[("*", "g2")]["matched"], 0)
        self.assertIsNone(rows[("*", "g2")]["mean"])
        self.assertEqual(rows[("*", "all")]["samples"], 16)

    def test_unknown_sizes(self):
        rows = self.stats({"g0": 4})
        self.assertIsNone(rows[("*", "g1")]["matched_pct"])
        self.assertIsNone(rows[("*", "all")]["samples"])

    def test_tsv_and_reports(self):
        r = KmindexQueryResult(items=self.ITEMS, index_sizes={"g0": 4, "g1": 2})
        lines = r.generate_stats_tsv(0.05).split("\n")
        self.assertEqual(lines[0], "\t".join(KmindexQueryResult._STATS_HEADERS))
        self.assertEqual(lines[-1], "*\tall\t6\t3\t50.0\t1\t0.600\t0.600")
        self.assertIn("## Statistics", r.generate_markdown(0.05))
        self.assertIn("<h2>Statistics</h2>", r.generate_html(0.05))


if __name__ == "__main__":
    unittest.main()