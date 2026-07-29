import json
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import yaml

from pykmhelpers.core.constants import DATA_EXT
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.utils import Toolbox

logger = logging.getLogger(__name__)

KMINDEX_QUERY_OUTPUT = "kmindex_output"


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

    _CONVERTERS: dict[str, str] = {
        "md": "generate_markdown",
        "html": "generate_html",
        "tsv": "generate_tsv",
        "json": "generate_json",
        "yaml": "generate_yaml",
    }

    def __init__(
        self, file: Optional[str] = None, items: Optional[dict] = None
    ) -> None:
        self._items = items or {}
        if file:
            self.load_jsonl(file)

    @property
    def items(self):
        return self._items

    def get_index_result(self, index_id) -> "KmindexQueryResult":
        items = {index_id: self._items[index_id]} if index_id in self._items else {}
        return KmindexQueryResult(items=items)

    def __eq__(self, other) -> bool:
        if not isinstance(other, KmindexQueryResult):
            return False
        return self._items == other._items

    def load_jsonl(self, file):
        # Each line is a record: {"index": ..., "query": ..., "samples": {...}}
        # Records are grouped by index into {index: {query: samples}}.
        with open(file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                index = record["index"]
                query = record["query"]
                samples = record["samples"]
                if index and query and samples:
                    self._items.setdefault(index, {})[query] = samples

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
        return "\n".join(lines)

    @classmethod
    def _score_style(cls, score: float) -> str:
        # Map a 0..1 score onto a ramp step, plus a readable text color
        ramp = cls._SCORE_RAMP
        step = min(int(max(score, 0.0) * len(ramp)), len(ramp) - 1)
        fg = "#ffffff" if step >= cls._SCORE_RAMP_INVERT else "#0b0b0b"
        return f"background-color: {ramp[step]}; color: {fg}"

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
        body = (
            # f"    <h2>kmindex results - Filter scores ≥ {threshold}</h2>\n"
            # f"    <table>\n"
            # f"        <tr><th>Query</th><th>Sample</th><th>Location</th><th>Score</th></tr>\n"
            # f"{row_html}\n"
            # f"    </table>\n"
            f"    <h2>Score matrix</h2>\n"
            f"    <table>\n"
            f"        <tr><th>Sequence \\ Sample</th>{matrix_header}</tr>\n"
            f"{matrix_html}\n"
            f"    </table>\n"
            f"    <div class='legend'>\n"
            f"        <span>0.000</span><span class='scale'></span><span>1.000</span>\n"
            f"    </div>"
        )
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

    def _by_sample(self, threshold: float) -> dict[str, dict[str, dict[str, float]]]:
        # {index: {sample: {query: score}}}, scores below threshold dropped
        pivoted: dict[str, dict[str, dict[str, float]]] = {}
        for index_name, queries in self._items.items():
            samples_map = pivoted.setdefault(index_name, {})
            for query_name, samples in queries.items():
                for sample, score in samples.items():
                    if score >= threshold:
                        samples_map.setdefault(sample, {})[query_name] = score
        return pivoted

    def generate_json(self, threshold: float = 0.0) -> str:
        return json.dumps(self._by_sample(threshold), indent=2)

    def generate_yaml(self, threshold: float = 0.0) -> str:
        filtered = {
            index_name: {
                sample: {q: round(sc, 3) for q, sc in queries.items()}
                for sample, queries in samples.items()
            }
            for index_name, samples in self._by_sample(threshold).items()
        }
        return yaml.dump(filtered, default_flow_style=False, sort_keys=False)

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

        # Save result to info.yaml
        info_file = os.path.join(output_dir, "info.yaml")
        with open(info_file, "w") as f:
            yaml.safe_dump(output, f)

        result = []

        for f in os.listdir(result_dir):
            fpath = os.path.join(result_dir, f)
            if os.path.isfile(fpath) and f.endswith(".jsonl"):
                try:
                    result.append(KmindexQueryResult(fpath))
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
            self._convert_results(result_dir)

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

    def _convert_results(self, result_dir: str) -> None:
        fmt = self._config.output_format
        out_file = os.path.join(os.path.dirname(result_dir), f"results.{fmt}")
        logger.debug(f"Merge results to {out_file}...")
        threshold = self._config.threshold
        merged = KmindexQueryResult()
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
