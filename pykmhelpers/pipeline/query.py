import json
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from itertools import groupby
from typing import Callable, Iterable, Optional

import yaml

from pykmhelpers.core.constants import DATA_EXT
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.utils import Toolbox

logger = logging.getLogger(__name__)

KMINDEX_QUERY_OUTPUT = "kmindex_output"


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
        ("command", "Command"),
        ("execution_time_s", "Execution time (s)"),
        ("max_cpu_percent", "Max CPU (%)"),
        ("max_memory_mb", "Max memory (MB)"),
    )

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
    ) -> None:
        self._items = items or {}
        # {index: {query: {sample: [0/1 per k-mer]}}}, only filled by jsonl_vec input
        self._vectors: dict[str, dict[str, dict[str, list[int]]]] = vectors or {}
        # Run info reported by the kmindex wrapper (command, timing, resources)
        self._metadata: dict = metadata or {}
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

    def _rows(self, threshold: float) -> list[tuple[str, str, str, float]]:
        # Flattened (query, sample, location, score) rows, sorted by query then score desc
        rows = []
        for index_name, queries in self._items.items():
            for query_name, samples in queries.items():
                for sample, score in samples.items():
                    if score >= threshold:
                        rows.append((query_name, sample, index_name, score))
        rows.sort(key=lambda r: (r[0], -r[3]))
        return rows

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

    def generate_coverage_tsv(self, threshold: float = 0.0) -> str:
        lines = ["\t".join(self._COVERAGE_HEADERS + ("runs",))]
        cells = self._coverage_cells(self._vector_rows(threshold), with_runs=True)
        lines.extend("\t".join(row) for row in cells)
        return "\n".join(lines)

    def _metadata_rows(self) -> list[tuple[str, str]]:
        # Only the fields actually reported, dry runs carry the command alone
        return [
            (label, str(self._metadata[key]))
            for key, label in self._RUN_FIELDS
            if self._metadata.get(key) is not None
        ]

    def generate_markdown(self, threshold: float = 0.0) -> str:
        rows = self._rows(threshold)
        headers = ("Query", "Sample", "Location")
        widths = [
            max([len(h)] + [len(str(row[i])) for row in rows])
            for i, h in enumerate(headers)
        ]
        lines = []

        # lines.append(f"## kmindex results - Filter scores ≥ {threshold}\n")
        # lines.append(
        #     "| "
        #     + " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths))
        #     + " | Score |"
        # )
        # lines.append("| " + " | ".join("-" * w for w in widths) + " | ----- |")
        # for query_name, sample, index_name, score in rows:
        #     lines.append(
        #         f"| {query_name:<{widths[0]}} | {sample:<{widths[1]}} "
        #         f"| {index_name:<{widths[2]}} | {score:.3f} |"
        #     )
        # lines.append("")

        meta = self._metadata_rows()
        if meta:
            lines.append("## Run\n")
            for label, value in meta:
                lines.append(f"- {label}: `{value}`")
            lines.append("")

        query_names, sample_names, scores = self._matrix(threshold)
        corner = "Sequence \\ Sample"
        q_w = max([len(corner)] + [len(q) for q in query_names])
        s_ws = [max(len(s), len("0.000")) for s in sample_names]
        # lines.append("## Score matrix\n")
        lines.append(
            f"| {corner:<{q_w}} | "
            + " | ".join(f"{s:<{w}}" for s, w in zip(sample_names, s_ws))
            + " |"
        )
        lines.append(f"| {'-' * q_w} | " + " | ".join("-" * w for w in s_ws) + " |")
        for query in query_names:
            cells = [
                f"{scores[s][query]:.3f}".ljust(w) if query in scores[s] else " " * w
                for s, w in zip(sample_names, s_ws)
            ]
            lines.append(f"| {query:<{q_w}} | " + " | ".join(cells) + " |")
        lines.append("")

        rows = self._vector_rows(threshold)
        coverage = [
            cells + [f"`{self._track_text(row[4])}`"]
            for cells, row in zip(self._coverage_cells(rows), rows)
        ]
        if coverage:
            headers = self._COVERAGE_HEADERS + ("k-mer presence",)
            widths = [
                max([len(h)] + [len(row[i]) for row in coverage])
                for i, h in enumerate(headers)
            ]
            lines.append("## Coverage\n")
            lines.append(
                f"Track: {self._TRACK_TEXT_WIDTH} buckets along the query, "
                "`+` all k-mers found, `~` partial, `-` none.\n"
            )
            lines.append(
                "| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths)) + " |"
            )
            lines.append("| " + " | ".join("-" * w for w in widths) + " |")
            for row in coverage:
                lines.append(
                    "| " + " | ".join(f"{c:<{w}}" for c, w in zip(row, widths)) + " |"
                )
            lines.append("")
        return "\n".join(lines)

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

    def _coverage_html(self, threshold: float) -> str:
        rows = self._vector_rows(threshold)
        if not rows:
            return ""
        header = "".join(f"<th>{h}</th>" for h in self._COVERAGE_HEADERS)
        body = "\n".join(
            "        <tr>"
            + "".join(f"<td>{c}</td>" for c in cells)
            + f"<td class='track-cell'>{self._track_html(row[4])}</td></tr>"
            for cells, row in zip(self._coverage_cells(rows), rows)
        )
        return (
            f"    <h2>Coverage</h2>\n"
            f"    <table>\n"
            f"        <tr>{header}<th>k-mer presence</th></tr>\n"
            f"{body}\n"
            f"    </table>"
        )

    def generate_html(self, threshold: float = 0.0) -> str:
        row_html = "\n".join(
            f"        <tr><td>{q}</td><td>{s}</td><td>{loc}</td><td>{sc:.3f}</td></tr>"
            for q, s, loc, sc in self._rows(threshold)
        )
        query_names, sample_names, scores = self._matrix(threshold)
        matrix_header = "".join(f"<th>{s}</th>" for s in sample_names)
        matrix_html = "\n".join(
            f"        <tr><td>{query}</td>"
            + "".join(
                (
                    f"<td style='{self._score_style(scores[s][query])}'>"
                    f"{scores[s][query]:.3f}</td>"
                    if query in scores[s]
                    else "<td class='empty'>-</td>"
                )
                for s in sample_names
            )
            + "</tr>"
            for query in query_names
        )
        meta_html = "".join(
            f"        <tr><th>{label}</th><td class='run-value'>{value}</td></tr>\n"
            for label, value in self._metadata_rows()
        )
        if meta_html:
            meta_html = (
                f"    <h2>Run</h2>\n"
                f"    <table class='run'>\n{meta_html}    </table>\n"
            )
        body = (
            # f"    <h2>kmindex results - Filter scores ≥ {threshold}</h2>\n"
            # f"    <table>\n"
            # f"        <tr><th>Query</th><th>Sample</th><th>Location</th><th>Score</th></tr>\n"
            # f"{row_html}\n"
            # f"    </table>\n"
            f"{meta_html}"
            f"    <h2>Score matrix</h2>\n"
            f"    <table>\n"
            f"        <tr><th>Sequence \\ Sample</th>{matrix_header}</tr>\n"
            f"{matrix_html}\n"
            f"    </table>\n"
            f"    <div class='legend'>\n"
            f"        <span>0.000</span><span class='scale'></span><span>1.000</span>\n"
            f"    </div>"
        )
        coverage_html = self._coverage_html(threshold)
        if coverage_html:
            body = f"{body}\n{coverage_html}"
        return (
            f"<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
            f"    <meta charset='UTF-8'>\n"
            f"    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
            f"    <title>kmindex Results - {', '.join(self._items)}</title>\n"
            f"    <style>\n"
            f"        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}\n"
            f"        h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 30px; }}\n"
            f"        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}\n"
            f"        th, td {{ padding: 10px; text-align: center; border-bottom: 1px solid #ddd; }}\n"
            f"        th:first-child, td:first-child {{ text-align: left; }}\n"
            f"        th {{ background-color: #3498db; color: white; font-weight: bold; position: sticky; top: 0; }}\n"
            f"        tr:nth-child(even) td.empty {{ background-color: #f9f9f9; }}\n"
            f"        td.empty {{ color: #52514e; }}\n"
            f"        .legend {{ display: flex; align-items: center; gap: 8px; "
            f"font-size: 0.85em; color: #52514e; }}\n"
            f"        .legend .scale {{ width: 200px; height: 12px; border-radius: 2px; "
            f"background: linear-gradient(to right, {', '.join(self._SCORE_RAMP)}); }}\n"
            f"        table.run {{ width: auto; }}\n"
            f"        table.run th {{ background-color: #ecf0f1; color: #2c3e50; "
            f"text-align: left; position: static; }}\n"
            f"        td.run-value {{ text-align: left; font-family: monospace; "
            f"word-break: break-all; }}\n"
            f"        td.track-cell {{ width: 40%; padding: 6px 10px; }}\n"
            f"        .track {{ display: flex; height: 14px; border-radius: 2px; overflow: hidden; }}\n"
            f"        .track span {{ flex: 1 1 0; }}\n"
            f"    </style>\n</head>\n<body>\n"
            f"{body}\n"
            f"</body>\n</html>"
        )

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
        """
        index_ids = index_ids if index_ids is not None else []
        result_dir = os.path.join(output_dir, KMINDEX_QUERY_OUTPUT)
        os.makedirs(output_dir, exist_ok=True)

        query_path = os.path.join(output_dir, os.path.basename(self._path))
        shutil.copy(self._path, query_path)

        output = KmindexWrapper().query(
            input_registry=registry_path,
            query_file=query_path,
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
        self.info = output or {}

        # Save result to info.yaml
        info_file = os.path.join(output_dir, "info.yaml")
        with open(info_file, "w") as f:
            yaml.safe_dump(output, f)

        result = []

        for f in os.listdir(result_dir):
            fpath = os.path.join(result_dir, f)
            if os.path.isfile(fpath) and f.endswith(".jsonl"):
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
        output_format: Output format for result conversion (``json``, ``yaml``, ``md``, ``html``, ``tsv``).
        timestamp: Append a ``YYYYmmdd_HHMMSS`` suffix to each per-query output directory.
        on_existing: Behaviour when the output directory already exists
            (``skip``, ``fail``, ``delete``, ``new-name``).
        parallel: Parallelisation strategy passed to kmindex (``seq`` or ``sub``).
            Forced to ``sub`` when ``compressed`` is ``True``.
        force: Skip confirmation prompts (e.g. when ``on_existing="delete"``).
        print_output: Write converted results to stdout instead of saving to
            file.  Only meaningful when ``format`` is not ``json``.
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
    output_format: str = "json"
    timestamp: bool = False
    on_existing: str = "skip"
    parallel: str = "seq"
    force: bool = False
    vec: bool = False
    print_output: bool = False
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
        if self._config.compressed and self._config.parallel != "sub":
            logger.warning(
                "--compressed requires sub parallelization strategy; forcing parallel=sub"
            )
            self._config.parallel = "sub"

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
        errors: list[str] = []
        try:

            if self._config.batch:
                batch_path = os.path.join(tempfile.gettempdir(), "kmhelpers_batch.fa")
                temp_files.append(batch_path)
                with open(batch_path, "wb") as fout:
                    for qfile in resolved:
                        with open(qfile, "rb") as fin:
                            data = fin.read()
                        fout.write(data)
                        if not data.endswith(b"\n"):
                            fout.write(b"\n")
                logger.info(f"Batching {len(resolved)} file(s) into a single query...")
                result = self._run_single_safe(batch_path, total=1, idx=1)
                if result:
                    all_results.append(result)
                else:
                    errors.append(f"{os.path.basename(batch_path)}")
            else:
                total = len(resolved)
                for idx, qfile in enumerate(resolved, 1):
                    result = self._run_single_safe(qfile, total=total, idx=idx)
                    if result:
                        all_results.append(result)
                    else:
                        errors.append(f"{os.path.basename(qfile)}")
        finally:
            for tmp in temp_files:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        if errors:
            raise RuntimeError(
                f"{len(errors)} query file(s) failed: " + "; ".join(errors)
            )

        return all_results

    # ---
    # PRIVATE METHODS

    def _resolve_files(self, query_files: Iterable[str]) -> tuple[list[str], list[str]]:
        resolved: list[str] = []
        temp_files: list[str] = []
        for qfile in query_files:
            if qfile == "-":
                tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".fa", delete=False)
                tmp.write(sys.stdin.buffer.read())
                tmp.close()
                resolved.append(tmp.name)
                temp_files.append(tmp.name)
            elif os.path.isdir(qfile):
                for root, _, files in os.walk(qfile):
                    for fname in sorted(files):
                        if any(fname.endswith(ext) for ext in DATA_EXT):
                            resolved.append(os.path.join(root, fname))
            else:
                if not os.path.isfile(qfile):
                    raise FileNotFoundError(f"Query file not found: {qfile}")
                resolved.append(qfile)
        return resolved, temp_files

    def _run_single_safe(self, qfile: str, total: int, idx: int):
        try:
            result = self._run_single(qfile, total=total, idx=idx)
            return result
        except Exception as e:
            logger.error(f"[{os.path.basename(qfile)}] {e}")
            return None

    def _run_single(
        self, qfile: str, total: int, idx: int
    ) -> list["KmindexQueryResult"]:
        start = time.time()
        cfg = self._config

        stem = os.path.splitext(os.path.basename(qfile))[0]
        query_output = os.path.join(cfg.output_dir, stem)

        if cfg.timestamp:
            query_output = f"{query_output}_{time.strftime('%Y%m%d_%H%M%S')}"

        query_output = self._resolve_existing(query_output, stem)
        if query_output is None:
            return []

        logger.info(f"[{idx}/{total}] Querying: {stem}...")

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
        )

        elapsed = time.time() - start
        result_dir = os.path.join(query_output, KMINDEX_QUERY_OUTPUT)
        logger.debug(f"kmindex output dir: {result_dir}")
        logger.info(f"Time: {elapsed:.2f}s")

        if cfg.output_format:
            self._convert_results(result_dir, kq.info)

        if cfg.on_result is not None:
            cfg.on_result(results)

        return results

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
        logger.debug(f"Merge results to {out_file}...")
        threshold = self._config.threshold
        merged = KmindexQueryResult(metadata=info)
        for fname in sorted(os.listdir(result_dir)):
            if not fname.endswith(".jsonl"):
                continue
            json_path = os.path.join(result_dir, fname)
            try:
                merged.load_jsonl(json_path)
            except Exception as e:
                logger.warning(f"Failed to read {fname}: {e}")
        if not merged.items:
            logger.info(f"No match")
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
