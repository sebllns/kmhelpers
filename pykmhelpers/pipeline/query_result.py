"""Parsed kmindex query results: statistics and data formats."""

import json
import logging
import re
import statistics
from itertools import groupby
from typing import Optional

import yaml

from pykmhelpers.pipeline.query_report import QueryReport

logger = logging.getLogger(__name__)


class _InlineList(list):
    """List kept on a single line by the yaml dumper."""


class _QueryDumper(yaml.SafeDumper):
    pass


_QueryDumper.add_representer(
    _InlineList,
    lambda dumper, data: dumper.represent_sequence(
        "tag:yaml.org,2002:seq", data, flow_style=True
    ),
)


class KmindexQueryResult:
    # Match statistics columns, a score this close to 1 counts as perfect
    _STATS_HEADERS = (
        "query",
        "samples",
        "matched",
        "matched_pct",
        "perfect",
        "mean",
        "median",
        "best_sample",
        "best_score",
    )
    _PERFECT = 1.0 - 1e-9

    _CONVERTERS: dict[str, str] = {
        "md": "generate_markdown",
        "html": "generate_html",
        "tsv": "generate_tsv",
        "json": "generate_json",
        "yaml": "generate_yaml",
    }

    def __init__(
        self,
        file: Optional[str] = None,
        items: Optional[dict] = None,
        vectors: Optional[dict] = None,
        metadata: Optional[dict] = None,
        index_sizes: Optional[dict] = None,
    ) -> None:
        self._items = items or {}
        # {index: {query: {sample: [0/1 per k-mer]}}}, only filled by jsonl_vec input
        self._vectors: dict[str, dict[str, dict[str, list[int]]]] = vectors or {}
        # Run info reported by the kmindex wrapper (command, timing, resources)
        self._metadata: dict = metadata or {}
        # {index: number of samples}, from the registry, needed for matched_pct
        self._index_sizes: dict[str, int] = index_sizes or {}
        # Every query read, matched or not, so reports list them all
        self._queries: set[str] = set()
        if file:
            self.load_jsonl(file)

    @property
    def items(self):
        return self._items

    @property
    def metadata(self) -> dict:
        return self._metadata

    @metadata.setter
    def metadata(self, value: Optional[dict]) -> None:
        self._metadata = value or {}

    @property
    def index_sizes(self) -> dict:
        return self._index_sizes

    @index_sizes.setter
    def index_sizes(self, value: Optional[dict]) -> None:
        self._index_sizes = value or {}

    @property
    def vectors(self):
        return self._vectors

    @property
    def has_vectors(self) -> bool:
        return bool(self._vectors)

    def get_index_result(self, index_id) -> "KmindexQueryResult":
        items = {index_id: self._items[index_id]} if index_id in self._items else {}
        vectors = (
            {index_id: self._vectors[index_id]} if index_id in self._vectors else {}
        )
        return KmindexQueryResult(items=items, vectors=vectors)

    def __eq__(self, other) -> bool:
        # Scores only: a jsonl_vec result equals the plain jsonl result it derives from.
        if not isinstance(other, KmindexQueryResult):
            return False
        return self._items == other._items

    @staticmethod
    def _parse_sample(value) -> tuple[Optional[float], Optional[list[int]]]:
        # jsonl gives a plain score, jsonl_vec gives {"P": [0/1, ...], "R": score}
        if isinstance(value, bool):
            return None, None
        if isinstance(value, (int, float)):
            return float(value), None
        if isinstance(value, dict):
            vector = value.get("P")
            score = value.get("R")
            if score is None and vector:
                score = sum(vector) / len(vector)
            if score is None:
                return None, None
            return float(score), vector
        return None, None

    def load_jsonl(self, file):
        # Each line is a record: {"index": ..., "query": ..., "samples": {...}}
        # Records are grouped by index into {index: {query: {sample: score}}}.
        with open(file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                index = record["index"]
                query = record["query"]
                samples = record["samples"]
                if query:
                    self._queries.add(query)
                if not (index and query and samples):
                    continue
                scores = self._items.setdefault(index, {}).setdefault(query, {})
                for sample, value in samples.items():
                    score, vector = self._parse_sample(value)
                    if score is None:
                        logger.warning(
                            f"Unsupported sample entry for {index}/{query}/{sample}, skipped"
                        )
                        continue
                    scores[sample] = score
                    if vector:
                        self._vectors.setdefault(index, {}).setdefault(query, {})[
                            sample
                        ] = vector
                if not scores:
                    del self._items[index][query]

    def max_score(self, sample):
        max_score = 0
        for queries in self._items.values():
            for samples in queries.values():
                max_score = max(max_score, samples.get(sample, 0))
        return max_score

    def _matrix(self, threshold: float) -> tuple[list[str], list[str], dict]:
        # Sample x query score matrix, max score across indices
        # Queries and samples sorted by name
        scores: dict[str, dict[str, float]] = {}
        for queries in self._items.values():
            for query_name, samples in queries.items():
                for sample, score in samples.items():
                    if score >= threshold:
                        row = scores.setdefault(sample, {})
                        row[query_name] = max(row.get(query_name, 0), score)
        query_names = sorted({q for row in scores.values() for q in row})
        sample_names = sorted(scores)
        return query_names, sample_names, scores

    @staticmethod
    def _vector_stats(vector: list[int]) -> dict:
        # Coverage summary of a per-k-mer presence vector
        n = len(vector)
        covered = 0
        longest_run = 0
        run = 0
        gaps = 0
        previous = 1
        for v in vector:
            if v:
                covered += 1
                run += 1
                longest_run = max(longest_run, run)
            else:
                run = 0
                if previous:
                    gaps += 1
            previous = v
        return {
            "n_kmers": n,
            "covered": covered,
            "ratio": covered / n if n else 0.0,
            "longest_run": longest_run,
            "gaps": gaps,
        }

    @staticmethod
    def _rle(vector: list[int]) -> list[list[int]]:
        # Run-length encoding: [[value, count], ...]
        return [[value, len(list(group))] for value, group in groupby(vector)]

    def _vector_rows(
        self, threshold: float
    ) -> list[tuple[str, str, str, float, list[int]]]:
        # (query, sample, index, score, vector) rows, sorted by query then score desc
        rows = []
        for index_name, queries in self._vectors.items():
            for query_name, samples in queries.items():
                for sample, vector in samples.items():
                    score = (
                        self._items.get(index_name, {}).get(query_name, {}).get(sample)
                    )
                    if score is not None and score >= threshold:
                        rows.append((query_name, sample, index_name, score, vector))
        rows.sort(key=lambda r: (r[0], -r[3]))
        return rows

    _COVERAGE_HEADERS = (
        "query",
        "sample",
        "index",
        "R",
        "n_kmers",
        "covered",
        "longest_run",
        "gaps",
    )

    @classmethod
    def _coverage_cells(cls, rows, with_runs: bool = False) -> list[list[str]]:
        # One string cell list per row of _vector_rows, matching _COVERAGE_HEADERS
        cells = []
        for query, sample, index_name, score, vector in rows:
            stats = cls._vector_stats(vector)
            row = [
                query,
                sample,
                index_name,
                f"{score:.3f}",
                str(stats["n_kmers"]),
                str(stats["covered"]),
                str(stats["longest_run"]),
                str(stats["gaps"]),
            ]
            if with_runs:
                row.append(json.dumps(cls._rle(vector), separators=(",", ":")))
            cells.append(row)
        return cells

    @classmethod
    def _stats_row(cls, query: str, size: Optional[int], hits: dict) -> dict:
        # hits: {sample: score}, matches of one query (or best over all queries)
        scores = list(hits.values())
        best = max(hits, key=hits.get) if hits else None
        return {
            "query": query,
            "samples": size,
            "matched": len(scores),
            "matched_pct": 100 * len(scores) / size if size else None,
            "perfect": sum(s >= cls._PERFECT for s in scores),
            "mean": statistics.fmean(scores) if scores else None,
            "median": statistics.median(scores) if scores else None,
            "best_sample": best,
            "best_score": hits[best] if best is not None else None,
        }

    def query_names(self) -> list[str]:
        """All queries seen, including those without any match, in natural
        order (read_2 before read_10)."""
        names = set(self._queries)
        for queries in self._items.values():
            names.update(queries)
        return sorted(
            names,
            key=lambda n: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", n)],
        )

    def total_samples(self) -> Optional[int]:
        """Samples in the queried subindexes, None if any size is unknown."""
        sizes = self._index_sizes
        indexes = set(sizes) | set(self._items)
        if indexes and all(i in sizes for i in indexes):
            return sum(sizes[i] for i in indexes)
        return None

    def _query_hits(self, threshold: float) -> dict[str, dict[str, tuple]]:
        # {query: {sample: (score, vector or None)}}, best score over subindexes
        hits: dict[str, dict[str, tuple]] = {}
        for index, queries in self._items.items():
            index_vectors = self._vectors.get(index, {})
            for query, samples in queries.items():
                query_hits = hits.setdefault(query, {})
                for sample, score in samples.items():
                    if score >= threshold and score > query_hits.get(sample, (-1,))[0]:
                        vector = index_vectors.get(query, {}).get(sample)
                        query_hits[sample] = (score, vector)
        return hits

    def match_stats(self, threshold: float = 0.0) -> list[dict]:
        """One row per query over the whole index, then a "*" row over all
        queries, where each sample counts once with its best score."""
        total = self.total_samples()
        hits = self._query_hits(threshold)
        rows = []
        best: dict[str, float] = {}
        for query in self.query_names():
            scores = {s: v[0] for s, v in hits.get(query, {}).items()}
            rows.append(self._stats_row(query, total, scores))
            for sample, score in scores.items():
                best[sample] = max(best.get(sample, 0.0), score)
        rows.append(self._stats_row("*", total, best))
        return rows

    @staticmethod
    def _stats_cells(row: dict, headers: tuple[str, ...]) -> list[str]:
        cells = []
        for key in headers:
            value = row[key]
            if value is None:
                cells.append("")
            elif key == "matched_pct":
                cells.append(f"{value:.1f}")
            elif isinstance(value, float):
                cells.append(f"{value:.3f}")
            else:
                cells.append(str(value))
        return cells

    def generate_stats_tsv(self, threshold: float = 0.0) -> str:
        lines = ["\t".join(self._STATS_HEADERS)]
        for row in self.match_stats(threshold):
            lines.append("\t".join(self._stats_cells(row, self._STATS_HEADERS)))
        return "\n".join(lines)

    def generate_coverage_tsv(self, threshold: float = 0.0) -> str:
        lines = ["\t".join(self._COVERAGE_HEADERS + ("runs",))]
        cells = self._coverage_cells(self._vector_rows(threshold), with_runs=True)
        lines.extend("\t".join(row) for row in cells)
        return "\n".join(lines)

    def generate_report(
        self,
        fmt: str,
        threshold: float = 0.0,
        page_size: int = 0,
        top: int = 100,
    ) -> dict[str, str]:
        """md or html report as {relative path: content}, see QueryReport.files."""
        return QueryReport(self).files(fmt, threshold, page_size, top)

    def generate_markdown(self, threshold: float = 0.0) -> str:
        return self.generate_report("md", threshold)["results.md"]

    def generate_html(self, threshold: float = 0.0) -> str:
        return self.generate_report("html", threshold)["results.html"]

    def generate_tsv(self, threshold: float = 0.0) -> str:
        query_names, sample_names, scores = self._matrix(threshold)
        lines = ["\t".join(["seq"] + sample_names)]
        for query in query_names:
            cells = [
                f"{scores[s][query]:.3f}" if query in scores[s] else ""
                for s in sample_names
            ]
            lines.append("\t".join([query] + cells))
        return "\n".join(lines)

    def _by_sample(self, threshold: float, with_rle: bool = False) -> dict:
        # {index: {sample: {query: entry}}}, scores below threshold dropped.
        # entry is the bare score, or a stats dict when a presence vector is known.
        pivoted: dict[str, dict[str, dict[str, object]]] = {}
        for index_name, queries in self._items.items():
            samples_map = pivoted.setdefault(index_name, {})
            for query_name, samples in queries.items():
                for sample, score in samples.items():
                    if score < threshold:
                        continue
                    vector = (
                        self._vectors.get(index_name, {})
                        .get(query_name, {})
                        .get(sample)
                    )
                    entry: object = score
                    if vector:
                        entry = {"R": score, **self._vector_stats(vector)}
                        if with_rle:
                            entry["P"] = self._rle(vector)
                    samples_map.setdefault(sample, {})[query_name] = entry
        return pivoted

    def generate_json(self, threshold: float = 0.0) -> str:
        return json.dumps(self._by_sample(threshold, with_rle=True), indent=2)

    def generate_yaml(self, threshold: float = 0.0) -> str:
        def rounded(entry):
            if isinstance(entry, dict):
                return {
                    k: (
                        _InlineList(v)
                        if k == "P"
                        else round(v, 3) if isinstance(v, float) else v
                    )
                    for k, v in entry.items()
                }
            return round(entry, 3)

        filtered = {
            index_name: {
                sample: {q: rounded(entry) for q, entry in queries.items()}
                for sample, queries in samples.items()
            }
            for index_name, samples in self._by_sample(threshold, with_rle=True).items()
        }
        return yaml.dump(
            filtered, Dumper=_QueryDumper, default_flow_style=False, sort_keys=False
        )

    def convert(self, format: str, threshold: float = 0.01) -> str:
        key = format.lower()
        if key not in self._CONVERTERS:
            raise ValueError(
                f"Unsupported output format: {format!r}. Use: {', '.join(self._CONVERTERS)}"
            )
        return getattr(self, self._CONVERTERS[key])(threshold)
