import heapq
import json
import logging
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from html import escape
from itertools import groupby
from typing import Callable, Iterable, Optional

import yaml

from pykmhelpers.core.constants import DATA_EXT_ALL, strip_data_ext
from pykmhelpers.core.kmindex_paths import get_json_path
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.utils import Toolbox, detect_compression, open_decompressed

logger = logging.getLogger(__name__)

KMINDEX_QUERY_OUTPUT = "kmindex_output"

# Compressions kmindex cannot read (only gz is, despite its help mentioning
# bzip2): bz2, xz and zst are decompressed before querying, zip is rejected
# by open_decompressed (multi-file archive)
_KMINDEX_UNREADABLE = (".bz2", ".xz", ".zst", ".zip")


def list_result_files(result_dir: str) -> list[str]:
    """Return the kmindex result files (JSON lines) found in result_dir.

    A single batch is written as <index>.jsonl at the top level. Several
    batches go to batch_N/<index>.json[l], kmindex only merges them with
    --aggregate, in which case the top-level files are used.
    """

    def scan(path: str) -> list[str]:
        return sorted(
            e.path
            for e in os.scandir(path)
            if e.is_file() and e.name.endswith((".jsonl", ".json"))
        )

    top = scan(result_dir)
    if top:
        return top
    files: list[str] = []
    for e in sorted(os.scandir(result_dir), key=lambda e: e.name):
        if e.is_dir() and e.name.startswith("batch_"):
            files.extend(scan(e.path))
    return files


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


def _slug(name: str, used: set[str]) -> str:
    """Anchor id for a sequence name, unique within used."""
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "seq"
    slug, i = base, 2
    while slug in used:
        slug, i = f"{base}-{i}", i + 1
    used.add(slug)
    return slug


class _ReportWriter:
    """Markdown primitives of a report, overridden by _HtmlWriter.
    Methods return markup, text() escapes raw values."""

    ext = "md"
    index_name = "README.md"

    @staticmethod
    def create(fmt: str) -> "_ReportWriter":
        if fmt == "md":
            return _ReportWriter()
        if fmt == "html":
            return _HtmlWriter()
        raise ValueError(f"No report for format {fmt!r}, use md or html")

    def text(self, value) -> str:
        return str(value).replace("|", "\\|")

    def code(self, value) -> str:
        return f"`{value}`"

    def link(self, text: str, href: str) -> str:
        return f"[{text}]({href})"

    def heading(self, level: int, text: str, anchor: Optional[str] = None) -> str:
        # Explicit anchor, renderers generate heading ids differently
        prefix = f'<a id="{anchor}"></a>\n\n' if anchor else ""
        return f"{prefix}{'#' * level} {text}\n"

    def para(self, text: str) -> str:
        return f"{text}\n"

    def items(self, entries: list[str]) -> str:
        return "".join(f"- {e}\n" for e in entries)

    def table(self, headers: list[str], rows: list[list[str]]) -> str:
        lines = [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(" --- " for _ in headers) + "|",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in rows)
        return "\n".join(lines) + "\n"

    def page(self, title: str, parts: list[str]) -> str:
        return "\n".join([f"# {title}\n"] + parts)


class _HtmlWriter(_ReportWriter):
    ext = "html"
    index_name = "index.html"

    _STYLE = (
        "body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }\n"
        "h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 30px; }\n"
        "table { border-collapse: collapse; margin: 20px 0; }\n"
        "th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #ddd; }\n"
        "th { background-color: #3498db; color: white; position: sticky; top: 0; }\n"
        "code { font-family: monospace; word-break: break-all; }\n"
        ".score { display: inline-block; min-width: 3.5em; padding: 2px 6px; border-radius: 2px; }\n"
        ".track { display: flex; width: 400px; height: 14px; border-radius: 2px; overflow: hidden; }\n"
        ".track span { flex: 1 1 0; }\n"
    )

    def text(self, value) -> str:
        return escape(str(value))

    def code(self, value) -> str:
        return f"<code>{escape(str(value))}</code>"

    def link(self, text: str, href: str) -> str:
        return f"<a href='{escape(href)}'>{text}</a>"

    def heading(self, level: int, text: str, anchor: Optional[str] = None) -> str:
        id_attr = f" id='{anchor}'" if anchor else ""
        return f"<h{level}{id_attr}>{text}</h{level}>"

    def para(self, text: str) -> str:
        return f"<p>{text}</p>"

    def items(self, entries: list[str]) -> str:
        return "<ul>\n" + "".join(f"<li>{e}</li>\n" for e in entries) + "</ul>"

    def table(self, headers: list[str], rows: list[list[str]]) -> str:
        head = "".join(f"<th>{h}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>\n" for row in rows
        )
        return f"<table>\n<tr>{head}</tr>\n{body}</table>"

    def page(self, title: str, parts: list[str]) -> str:
        body = "\n".join(parts)
        return (
            "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
            "<meta charset='UTF-8'>\n"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
            f"<title>{escape(title)}</title>\n"
            f"<style>\n{self._STYLE}</style>\n</head>\n<body>\n"
            f"<h1>{escape(title)}</h1>\n{body}\n</body>\n</html>\n"
        )


class KmindexQueryResult:
    # Sequential blue ramp, light (score 0) to dark (score 1)
    _SCORE_RAMP = (
        "#cde2fb",
        "#9ec5f4",
        "#6da7ec",
        "#3987e5",
        "#256abf",
        "#184f95",
        "#0d366b",
    )
    # From this step on, the background is dark enough to need light text
    _SCORE_RAMP_INVERT = 4
    # Coverage track: bucket count (html), character count (markdown),
    # and color of a fully absent bucket
    _TRACK_BUCKETS = 200
    _TRACK_TEXT_WIDTH = 120
    _TRACK_EMPTY = "#eeeeee"

    # Run info fields kept in reports, in display order
    _RUN_FIELDS: tuple[tuple[str, str], ...] = (
        ("date", "Date"),
        ("execution_time_s", "Runtime (s)"),
        ("max_cpu_percent", "Max CPU (%)"),
        ("max_memory_mb", "Max memory (MB)"),
        ("kmindex_version", "kmindex version"),
        ("registry", "Registry"),
        ("subindexes", "Subindexes"),
        ("samples", "Samples"),
        ("threshold", "Threshold"),
        ("zvalue", "z"),
        ("query_file", "Query file"),
        ("command", "Command"),
    )

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

    @staticmethod
    def _track_buckets(vector: list[int], width: int) -> list[tuple[int, int, float]]:
        # Downsample a presence vector to (start, end, mean) buckets
        n = len(vector)
        buckets = min(n, width)
        out = []
        for i in range(buckets):
            lo = i * n // buckets
            hi = max((i + 1) * n // buckets, lo + 1)
            chunk = vector[lo:hi]
            out.append((lo, hi, sum(chunk) / len(chunk)))
        return out

    @classmethod
    def _track_text(cls, vector: list[int]) -> str:
        # ASCII coverage track: + all found, ~ partial, - absent
        return "".join(
            "+" if mean == 1 else "-" if mean == 0 else "~"
            for _, _, mean in cls._track_buckets(vector, cls._TRACK_TEXT_WIDTH)
        )

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

    def _metadata_rows(self, threshold: float) -> list[tuple[str, str]]:
        # Only the fields actually reported, dry runs carry the command alone
        meta = dict(self._metadata)
        if meta.get("start_time") is not None:
            meta["date"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(meta["start_time"])
            )
        meta["threshold"] = threshold
        meta["samples"] = self.total_samples()
        if not meta.get("subindexes"):
            meta["subindexes"] = ", ".join(sorted(self._index_sizes or self._items))
        return [
            (label, str(meta[key]))
            for key, label in self._RUN_FIELDS
            if meta.get(key) not in (None, "")
        ]

    @classmethod
    def _score_style(cls, score: float) -> str:
        # Map a 0..1 score onto a ramp step, plus a readable text color
        ramp = cls._SCORE_RAMP
        step = min(int(max(score, 0.0) * len(ramp)), len(ramp) - 1)
        fg = "#ffffff" if step >= cls._SCORE_RAMP_INVERT else "#0b0b0b"
        return f"background-color: {ramp[step]}; color: {fg}"

    @classmethod
    def _track_html(cls, vector: list[int]) -> str:
        # Presence vector downsampled to fixed-width buckets, colored by bucket mean
        cells = []
        for lo, hi, mean in cls._track_buckets(vector, cls._TRACK_BUCKETS):
            style = (
                f"background-color: {cls._TRACK_EMPTY}"
                if mean == 0
                else cls._score_style(mean)
            )
            cells.append(f"<span style='{style}' title='{lo}-{hi}: {mean:.2f}'></span>")
        return f"<div class='track'>{''.join(cells)}</div>"

    # ---
    # MD / HTML REPORT

    _REPORT_TITLE = "kmindex query results"

    # Index and overall columns: stats key, label
    _REPORT_COLUMNS: tuple[tuple[str, str], ...] = (
        ("matched", "Matched"),
        ("matched_pct", "Matched %"),
        ("perfect", "Perfect"),
        ("mean", "Mean"),
        ("median", "Median"),
        ("best_sample", "Best sample"),
        ("best_score", "Best score"),
    )

    @staticmethod
    def _how_to_read(threshold: float, top: int, paged: bool) -> list[str]:
        where = "in the pages of `details/`" if paged else "below the sequence table"
        return [
            "Score: share of the query k-mers found in the sample, from 0 to 1.",
            f"A sample matches a sequence when its score is >= {threshold}. "
            "A perfect match has a score of 1.",
            "Matched % is relative to all samples of the queried subindexes. "
            "Mean and median are computed over the matching samples only.",
            "Overall: each sample counts once, with its best score over all sequences.",
            "Sequences: one line per query sequence, the name links to its details. "
            "Sequences without any match have no details.",
            f"Details ({where}): the {top} best samples of each sequence, by score.",
            "Full data: kmindex_output/ (raw JSON lines), stats.tsv (statistics per "
            "sequence).",
        ]

    def _cell(self, w: "_ReportWriter", key: str, cell: str) -> str:
        return w.code(cell) if key == "best_sample" and cell else w.text(cell)

    def _score_cell(self, w: "_ReportWriter", score: float) -> str:
        if w.ext == "html":
            return f"<span class='score' style='{self._score_style(score)}'>{score:.3f}</span>"
        return f"{score:.3f}"

    def _track_cell(self, w: "_ReportWriter", vector: Optional[list[int]]) -> str:
        if not vector:
            return ""
        return (
            self._track_html(vector)
            if w.ext == "html"
            else w.code(self._track_text(vector))
        )

    def _detail_section(
        self, w: "_ReportWriter", query: str, anchor: str, hits: dict, top: int
    ) -> str:
        shown = heapq.nlargest(top, hits.items(), key=lambda item: item[1][0])
        with_track = any(vector for _, (_, vector) in shown)
        headers = ["Sample", "Score"] + (["Coverage"] if with_track else [])
        rows = []
        for sample, (score, vector) in shown:
            row = [w.text(sample), self._score_cell(w, score)]
            if with_track:
                row.append(self._track_cell(w, vector))
            rows.append(row)
        parts = [w.heading(2, w.text(query), anchor)]
        if len(hits) > len(shown):
            parts.append(
                w.para(
                    f"{len(shown)} of {len(hits)} matching samples shown, "
                    f"all matches are in kmindex_output/."
                )
            )
        parts.append(w.table(headers, rows))
        return "\n".join(parts)

    def generate_report(
        self,
        fmt: str,
        threshold: float = 0.0,
        page_size: int = 0,
        top: int = 100,
    ) -> dict[str, str]:
        """Build a md or html report as {relative path: content}.

        Up to page_size sequences (or page_size 0): a single results.<fmt>.
        More: README.md or index.html, plus details/page_NNN.<fmt> holding
        page_size sequences each. Only the top best samples are listed per
        sequence, statistics use all matches.
        """
        w = _ReportWriter.create(fmt)
        hits = self._query_hits(threshold)
        stats = self.match_stats(threshold)
        overall = stats.pop()
        queries = [row["query"] for row in stats]
        paged = 0 < page_size < len(queries)
        n_pages = -(-len(queries) // page_size) if paged else 1
        digits = max(3, len(str(n_pages)))

        def page_path(page: int) -> str:
            return f"details/page_{page:0{digits}d}.{w.ext}"

        # Anchors and detail pages, only for sequences with a match
        used: set[str] = set()
        anchors: dict[str, str] = {}
        pages: dict[int, list[str]] = {}
        for pos, query in enumerate(queries):
            if not hits.get(query):
                continue
            anchors[query] = _slug(query, used)
            page = pos // page_size + 1 if paged else 0
            pages.setdefault(page, []).append(
                self._detail_section(w, query, anchors[query], hits[query], top)
            )

        keys = [key for key, _ in self._REPORT_COLUMNS]
        labels = [label for _, label in self._REPORT_COLUMNS]
        index_rows = []
        for pos, row in enumerate(stats):
            query = row["query"]
            name = w.text(query)
            if query in anchors:
                href = f"#{anchors[query]}"
                if paged:
                    href = f"{page_path(pos // page_size + 1)}{href}"
                name = w.link(name, href)
            cells = self._stats_cells(row, tuple(keys))
            index_rows.append(
                [name] + [self._cell(w, k, c) for k, c in zip(keys, cells)]
            )

        overall_cells = self._stats_cells(overall, tuple(keys))
        parts = [
            w.heading(2, "Run"),
            w.items(
                [
                    f"{label}: {w.code(value) if label == 'Command' else w.text(value)}"
                    for label, value in self._metadata_rows(threshold)
                ]
            ),
            w.heading(2, "Overall"),
            w.table(
                labels, [[self._cell(w, k, c) for k, c in zip(keys, overall_cells)]]
            ),
            w.heading(2, "How to read"),
            w.items(self._how_to_read(threshold, top, paged)),
            w.heading(2, f"Sequences ({len(queries)})"),
            w.table(["Sequence"] + labels, index_rows),
        ]
        if not paged:
            parts.extend(pages.get(0, []))
            return {f"results.{w.ext}": w.page(self._REPORT_TITLE, parts)}

        files = {w.index_name: w.page(self._REPORT_TITLE, parts)}
        for page, sections in pages.items():
            first = (page - 1) * page_size + 1
            last = min(page * page_size, len(queries))
            title = f"{self._REPORT_TITLE}, sequences {first} to {last}"
            back = w.para(w.link("Back to the index", f"../{w.index_name}"))
            files[page_path(page)] = w.page(title, [back] + sections)
        return files

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


class KmindexQuery:
    def __init__(self, path: str = "", sequence: Optional[Sequence] = None) -> None:
        if not path and sequence is None:
            raise ValueError("Either path or sequence must be provided")
        self._sequence = sequence
        self._path = path
        # Run info (command, timing, resources) filled by execute()
        self.info: dict = {}
        if sequence:
            if path:
                path = Toolbox.get_canonical_path(path)
                if os.path.isfile(path):
                    raise FileExistsError(f"Sequence file already exists: {path}")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(sequence.to_fasta())
        else:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Query file not found: {path}")

    def execute(
        self,
        registry_path: str,
        output_dir="query",
        index_ids: Optional[list[str]] = None,
        z: int = 6,
        threshold=0.01,
        single_query: Optional[str] = None,
        aggregate: bool = False,
        threads: int = 1,
        fast: bool = True,
        is_compressed: bool = False,
        method: str = "seq",
        vec: bool = False,
        keep_query: bool = False,
    ):
        """Run a query against the kmindex registry.

        Args:
            registry_path (str): Path to the kmindex registry.
            output_dir (str): Output directory for query results.
            index_ids (list[str]): Index IDs to query against; empty list queries all.
            z (int): Z-value (error rate parameter) for kmindex.
            threshold (float): Minimum score threshold for reported hits.
            single_query (str, optional): Query identifier; treats all sequences as one query.
            aggregate (bool): Whether to aggregate batch results into a single file.
            threads (int): Number of threads to use.
            fast (bool): Enable fast mode (disabled automatically when `is_compressed` is True).
            is_compressed (bool): Whether the index is stored in compressed form.
            method (str): Query method passed to kmindex (e.g. ``"seq"``).
            vec (bool): Use ``jsonl_vec`` output format instead of ``jsonl``.
            keep_query (bool): Copy the query file into ``output_dir``.
        """
        index_ids = index_ids if index_ids is not None else []
        result_dir = os.path.join(output_dir, KMINDEX_QUERY_OUTPUT)
        os.makedirs(output_dir, exist_ok=True)

        if keep_query:
            shutil.copy(self._path, output_dir)

        # info.yaml is written even on failure, with the error and kmindex output
        info: dict = {}
        try:
            info = (
                KmindexWrapper().query(
                    input_registry=registry_path,
                    query_file=self._path,
                    output_dir=result_dir,
                    names=index_ids,
                    single_query=single_query,
                    aggregate=aggregate,
                    threads=threads,
                    zvalue=z,
                    is_compressed=is_compressed,
                    fast=fast and not is_compressed,
                    threshold=threshold,
                    method=method,
                    format="jsonl_vec" if vec else "jsonl",
                )
                or {}
            )
        except Exception as e:
            info = dict(getattr(e, "result", None) or {})
            info["error"] = str(e)
            raise
        finally:
            info["query_file"] = os.path.abspath(self._path)
            self.info = info
            with open(os.path.join(output_dir, "info.yaml"), "w") as f:
                yaml.safe_dump(info, f)

        result = []

        files = list_result_files(result_dir)
        if not files:
            logger.warning(f"No kmindex result file in {result_dir}")
        for fpath in files:
            try:
                result.append(KmindexQueryResult(fpath, metadata=self.info))
            except Exception as e:
                logger.warning(f"Could not read result from {fpath}: {e}")

        return result


@dataclass
class QueryRunnerConfig:
    """Configuration for a ``QueryRunner`` instance.

    Attributes:
        registry_path: Path to the kmindex registry directory.
        output_dir: Root output directory; per-query subdirectories are created here.
        index_ids: Index IDs to query against.  Empty means all indices.
        zvalue: Z-value for the findere false-positive filter.
        threshold: Score threshold applied when filtering results.
        threads: Number of threads passed to kmindex.
        single_query: When set, all sequences are merged under this identifier.
        batch: Concatenate all input files into one query before running.
        aggregate: Aggregate batch results into a single output file.
        compressed: Whether the index is stored in compressed form.
        output_format: Data format of the converted results (``json``, ``yaml``,
            ``tsv``), ``None`` keeps only the raw kmindex results. ``md`` and
            ``html`` are deprecated, mapped to ``tsv`` plus ``export``.
        export: Human report written beside the data (``md``, ``html``),
            ``None`` for none. Requires ``output_format``.
        timestamp: Append a ``YYYYmmdd_HHMMSS`` suffix to each per-query output directory.
        on_existing: Behaviour when the output directory already exists
            (``skip``, ``fail``, ``delete``, ``new-name``).
        parallel: Parallelisation strategy passed to kmindex (``seq`` or ``sub``).
            Forced to ``sub`` when ``compressed`` is ``True``.
        force: Skip confirmation prompts (e.g. when ``on_existing="delete"``).
        print_output: Write the converted data to stdout instead of saving it
            to file. Reports are always written to files.
        keep_query: Copy each query file into its output directory.
        page_size: md/html reports, sequences per detail page; up to this
            count a single file is written. 0 disables paging.
        top: md/html reports, best samples listed per sequence.
        on_result: Optional callback invoked with each per-query result list as
            it completes.  Useful for streaming results to the caller without
            waiting for the full run to finish.
    """

    registry_path: str
    output_dir: str
    index_ids: list[str] = field(default_factory=list)
    zvalue: int = 6
    threshold: float = 0.05
    threads: int = 1
    single_query: Optional[str] = None
    batch: bool = False
    aggregate: bool = False
    compressed: bool = False
    output_format: Optional[str] = "json"
    export: Optional[str] = None
    timestamp: bool = False
    on_existing: str = "skip"
    parallel: str = "seq"
    force: bool = False
    vec: bool = False
    print_output: bool = False
    keep_query: bool = False
    page_size: int = 100
    top: int = 100
    on_result: Optional[Callable[[list["KmindexQueryResult"]], None]] = None


class QueryRunner:
    """Orchestrates one or more kmindex query operations.

    Accepts a list of query file paths (or ``"-"`` for stdin), resolves them to
    concrete files, optionally batches them, and runs each query via
    ``KmindexQuery``.  Output-directory conflict resolution, format conversion,
    and temp-file cleanup are all handled internally.

    Args:
        config: Runtime configuration.  See ``QueryRunnerConfig``.
    """

    def __init__(self, config: QueryRunnerConfig) -> None:
        self._config = config
        # info.yaml of the query in progress, reported on failure
        self._info_path: Optional[str] = None
        if self._config.compressed and self._config.parallel != "sub":
            logger.warning(
                "--compressed requires sub parallelization strategy; forcing parallel=sub"
            )
            self._config.parallel = "sub"
        if self._config.output_format in ("md", "html"):
            fmt = self._config.output_format
            logger.warning(
                f"Format {fmt} is deprecated as a data format, "
                f"use '-f tsv --export {fmt}'; writing both"
            )
            self._config.output_format = "tsv"
            self._config.export = fmt
        if self._config.export and not self._config.output_format:
            raise ValueError("An export requires a data format (output_format)")

    @property
    def config(self) -> QueryRunnerConfig:
        return self._config

    def run(self, query_files: Iterable[str]) -> list[list["KmindexQueryResult"]]:
        """Run queries for all provided input paths.

        Args:
            query_files: Paths to FASTA/FASTQ files or directories.  Pass
                ``"-"`` to read from stdin.

        Returns:
            A list of per-query result lists, in the same order as the resolved
            input files (one entry per executed query).
        """
        os.makedirs(self._config.output_dir, exist_ok=True)

        all_results: list[list[KmindexQueryResult]] = []

        resolved, temp_files = self._resolve_files(query_files)
        errors: list[tuple[str, str]] = []
        try:

            if self._config.batch:
                batch_path = os.path.join(tempfile.gettempdir(), "kmhelpers_batch.fa")
                temp_files.append(batch_path)
                with open(batch_path, "wb") as fout:
                    for qfile in resolved:
                        last = b"\n"
                        with open_decompressed(qfile) as fin:
                            while chunk := fin.read(1 << 20):
                                fout.write(chunk)
                                last = chunk[-1:]
                        if last != b"\n":
                            fout.write(b"\n")
                logger.info(f"Batching {len(resolved)} file(s) into a single query...")
                label = f"batch of {len(resolved)} file(s)"
                result, reason = self._run_single_safe(batch_path, 1, 1, label)
                if reason is None:
                    all_results.append(result)
                else:
                    errors.append((label, reason))
            else:
                total = len(resolved)
                for idx, qfile in enumerate(resolved, 1):
                    label = os.path.basename(qfile)
                    result, reason = self._run_single_safe(qfile, total, idx, label)
                    if reason is None:
                        all_results.append(result)
                    else:
                        errors.append((label, reason))
        finally:
            self._remove_temp(temp_files)

        if errors:
            lines = [f"  {label}: {reason}" for label, reason in errors]
            raise RuntimeError(
                f"{len(errors)} query file(s) failed:\n" + "\n".join(lines)
            )

        return all_results

    # ---
    # PRIVATE METHODS

    def _resolve_files(self, query_files: Iterable[str]) -> tuple[list[str], list[str]]:
        found: list[str] = []
        temp_files: list[str] = []
        for qfile in query_files:
            if qfile == "-":
                data = sys.stdin.buffer.read()
                suffix = ".fa" + detect_compression(data[:6])
                tmp = tempfile.NamedTemporaryFile(
                    mode="wb", suffix=suffix, delete=False
                )
                tmp.write(data)
                tmp.close()
                found.append(tmp.name)
                temp_files.append(tmp.name)
            elif os.path.isdir(qfile):
                for root, _, files in os.walk(qfile):
                    for fname in sorted(files):
                        if fname.endswith(DATA_EXT_ALL):
                            found.append(os.path.join(root, fname))
            else:
                if not os.path.isfile(qfile):
                    raise FileNotFoundError(f"Query file not found: {qfile}")
                found.append(qfile)

        resolved: list[str] = []
        try:
            for qfile in found:
                if qfile.endswith(_KMINDEX_UNREADABLE):
                    # Own temp dir keeps the base name, hence the output dir name
                    tmp_dir = tempfile.mkdtemp()
                    temp_files.append(tmp_dir)
                    name = os.path.basename(qfile)
                    tmp = os.path.join(tmp_dir, name[: name.rfind(".")])
                    with open_decompressed(qfile) as fin, open(tmp, "wb") as fout:
                        shutil.copyfileobj(fin, fout)
                    qfile = tmp
                resolved.append(qfile)
        except Exception:
            self._remove_temp(temp_files)
            raise
        return resolved, temp_files

    @staticmethod
    def _remove_temp(paths: list[str]) -> None:
        for path in paths:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)

    def _run_single_safe(
        self, qfile: str, total: int, idx: int, label: str
    ) -> tuple[list["KmindexQueryResult"], Optional[str]]:
        """Run one query, return (results, None) or ([], failure reason)."""
        self._info_path = None
        try:
            return self._run_single(qfile, total=total, idx=idx), None
        except Exception as e:
            logger.error(f"[{label}] {e}")
            logger.debug(f"[{label}] traceback:", exc_info=True)
            reason = f"{type(e).__name__}: {e}"
            if self._info_path and os.path.isfile(self._info_path):
                reason += f" - see {self._info_path}"
            return [], reason

    def _run_single(
        self, qfile: str, total: int, idx: int
    ) -> list["KmindexQueryResult"]:
        start = time.time()
        cfg = self._config

        stem = strip_data_ext(os.path.basename(qfile))
        query_output = os.path.join(cfg.output_dir, stem)

        if cfg.timestamp:
            query_output = f"{query_output}_{time.strftime('%Y%m%d_%H%M%S')}"

        query_output = self._resolve_existing(query_output, stem)
        if query_output is None:
            return []

        logger.info(f"[{idx}/{total}] Querying: {stem}...")

        self._info_path = os.path.join(query_output, "info.yaml")
        kq = KmindexQuery(path=qfile)
        results = kq.execute(
            registry_path=cfg.registry_path,
            output_dir=query_output,
            index_ids=cfg.index_ids,
            z=cfg.zvalue,
            single_query=cfg.single_query,
            aggregate=cfg.aggregate,
            threads=cfg.threads,
            is_compressed=cfg.compressed,
            fast=not cfg.compressed,
            threshold=cfg.threshold,
            method=cfg.parallel,
            vec=cfg.vec,
            keep_query=cfg.keep_query,
        )

        elapsed = time.time() - start
        result_dir = os.path.join(query_output, KMINDEX_QUERY_OUTPUT)
        logger.debug(f"kmindex output dir: {result_dir}")
        logger.info(f"Time: {elapsed:.2f}s")

        self._convert_results(result_dir, kq.info)

        if cfg.on_result is not None:
            cfg.on_result(results)

        return results

    def _registry_info(self) -> tuple[dict[str, int], dict]:
        """Samples per queried subindex and run info from the registry,
        both empty if the registry is unreadable."""
        try:
            with open(get_json_path(self._config.registry_path)) as f:
                registry = json.load(f)["index"]
        except (OSError, ValueError, KeyError) as e:
            logger.warning(f"Cannot read subindex sizes from the registry: {e}")
            return {}, {}
        names = [n for n in self._config.index_ids or list(registry) if n in registry]
        versions = sorted({str(registry[n].get("kmindex_version", "")) for n in names})
        info = {
            "registry": os.path.abspath(self._config.registry_path),
            "subindexes": ", ".join(names),
            "kmindex_version": ", ".join(v for v in versions if v),
        }
        return {n: registry[n]["nb_samples"] for n in names}, info

    def _resolve_existing(self, output_path: str, label: str) -> Optional[str]:
        """Return the (possibly adjusted) output path, or ``None`` to skip."""
        if not os.path.exists(output_path):
            return output_path

        strategy = self._config.on_existing

        if strategy == "skip":
            logger.warning(f"Skipping {label}: output directory already exists")
            return None
        elif strategy == "fail":
            raise FileExistsError(f"Output directory already exists: {output_path}")
        elif strategy == "delete":
            if not self._config.force:
                raise PermissionError(
                    f"Output directory exists and force=False: {output_path}. "
                    "Set force=True to delete automatically."
                )
            logger.debug(f"Deleting existing output directory: {output_path}")
            shutil.rmtree(output_path)
            return output_path
        elif strategy == "new-name":
            new_path = f"{output_path}_{time.strftime('%Y%m%d_%H%M%S')}"
            logger.debug(f"Output directory renamed to: {new_path}")
            return new_path

        return output_path

    def _convert_results(self, result_dir: str, info: Optional[dict] = None) -> None:
        fmt = self._config.output_format
        out_file = os.path.join(os.path.dirname(result_dir), f"results.{fmt}")
        threshold = self._config.threshold
        sizes, registry_info = self._registry_info()
        metadata = {**(info or {}), **registry_info, "zvalue": self._config.zvalue}
        merged = KmindexQueryResult(metadata=metadata, index_sizes=sizes)
        files = list_result_files(result_dir)
        for json_path in files:
            try:
                merged.load_jsonl(json_path)
            except Exception as e:
                logger.warning(f"Failed to read {json_path}: {e}")

        # Written even without match, the zero counts are informative
        if files and not self._config.print_output:
            stats_file = os.path.join(os.path.dirname(result_dir), "stats.tsv")
            with open(stats_file, "w") as f:
                f.write(merged.generate_stats_tsv(threshold))
            logger.info(f"Statistics: {stats_file}")

        if not merged.items and files:
            logger.info(
                f"No match above threshold {threshold} "
                f"({len(files)} result file(s) read)"
            )

        # Reports also list sequences without match, data formats need one
        if self._config.export and files:
            self._write_report(merged, os.path.dirname(result_dir))
        if not fmt or not merged.items:
            return
        converted = merged.convert(format=fmt, threshold=threshold)
        if self._config.print_output:
            sys.stdout.write(f"{converted}\n")
        else:
            with open(out_file, "w") as f:
                f.write(converted)
            logger.info(f"Results: {out_file}")

        # Other formats embed coverage, a matrix TSV cannot hold a second table
        if fmt == "tsv" and merged.has_vectors:
            coverage = merged.generate_coverage_tsv(threshold)
            if self._config.print_output:
                sys.stdout.write(f"{coverage}\n")
            else:
                coverage_file = os.path.join(
                    os.path.dirname(result_dir), "coverage.tsv"
                )
                with open(coverage_file, "w") as f:
                    f.write(coverage)
                logger.info(f"Coverage: {coverage_file}")

    def _write_report(self, merged: "KmindexQueryResult", out_dir: str) -> None:
        cfg = self._config
        files = merged.generate_report(
            cfg.export, cfg.threshold, page_size=cfg.page_size, top=cfg.top
        )
        for rel_path, content in files.items():
            path = os.path.join(out_dir, rel_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
        main = next(iter(files))
        detail = f" (+ {len(files) - 1} detail page(s))" if len(files) > 1 else ""
        logger.info(f"Report: {os.path.join(out_dir, main)}{detail}")
