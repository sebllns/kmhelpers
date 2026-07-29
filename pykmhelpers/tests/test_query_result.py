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


if __name__ == "__main__":
    unittest.main()