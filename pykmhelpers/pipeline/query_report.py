"""Human readable md / html reports of kmindex query results."""

import heapq
import re
import time
from html import escape
from typing import Optional


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

    _STYLE = """\
body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto;
  padding: 20px; }
h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;
  margin-top: 30px; }
table { border-collapse: collapse; margin: 20px 0; }
th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #ddd; }
th { background-color: #3498db; color: white; position: sticky; top: 0; }
code { font-family: monospace; word-break: break-all; }
.score { display: inline-block; min-width: 3.5em; padding: 2px 6px;
  border-radius: 2px; }
.track { display: flex; width: 400px; height: 14px; border-radius: 2px;
  overflow: hidden; }
.track span { flex: 1 1 0; }
"""

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


class QueryReport:
    """md or html report of a KmindexQueryResult."""

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

    def __init__(self, result) -> None:
        self._result = result

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

    def _metadata_rows(self, threshold: float) -> list[tuple[str, str]]:
        # Only the fields actually reported, dry runs carry the command alone
        meta = dict(self._result.metadata)
        if meta.get("start_time") is not None:
            meta["date"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(meta["start_time"])
            )
        meta["threshold"] = threshold
        meta["samples"] = self._result.total_samples()
        if not meta.get("subindexes"):
            meta["subindexes"] = ", ".join(
                sorted(self._result.index_sizes or self._result.items)
            )
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

    def _cell(self, w: _ReportWriter, key: str, cell: str) -> str:
        return w.code(cell) if key == "best_sample" and cell else w.text(cell)

    def _score_cell(self, w: _ReportWriter, score: float) -> str:
        if w.ext == "html":
            style = self._score_style(score)
            return f"<span class='score' style='{style}'>{score:.3f}</span>"
        return f"{score:.3f}"

    def _track_cell(self, w: _ReportWriter, vector: Optional[list[int]]) -> str:
        if not vector:
            return ""
        return (
            self._track_html(vector)
            if w.ext == "html"
            else w.code(self._track_text(vector))
        )

    def _detail_section(
        self, w: _ReportWriter, query: str, anchor: str, hits: dict, top: int
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

    def files(
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
        hits = self._result._query_hits(threshold)
        stats = self._result.match_stats(threshold)
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
            cells = self._result._stats_cells(row, tuple(keys))
            index_rows.append(
                [name] + [self._cell(w, k, c) for k, c in zip(keys, cells)]
            )

        overall_cells = self._result._stats_cells(overall, tuple(keys))
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
