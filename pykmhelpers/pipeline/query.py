import json
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import numpy as np
import yaml

from pykmhelpers.core.constants import DATA_EXT
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.utils import Toolbox

logger = logging.getLogger(__name__)


class KmindexQueryResult:
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
        # Scores are a float32 matrix: one row per query, one column per
        # sample, both sorted by name. 0.0 means no hit.
        self._queries: dict[str, int] = {}
        self._samples: dict[str, int] = {}
        self._scores = np.zeros((0, 0), dtype=np.float32)
        if items:
            pending: dict[int, list] = {}
            for query, samples in items.items():
                self._add_record(query, samples, pending)
            self._scatter(pending)
        if file:
            self.load_jsonl(file)

    @property
    def queries(self) -> list[str]:
        return list(self._queries)

    @property
    def samples(self) -> list[str]:
        return list(self._samples)

    @property
    def items(self) -> dict:
        # Nested {query: {sample: score}} of nonzero cells, built on demand.
        # Convenience for small results; avoid on millions of samples.
        names = self.samples
        result = {}
        for query, row in self._queries.items():
            scores = self._scores[row]
            result[query] = {
                names[c]: round(float(scores[c]), 3) for c in np.nonzero(scores)[0]
            }
        return result

    def score(self, query: str, sample: str) -> float:
        q = self._queries.get(query)
        s = self._samples.get(sample)
        if q is None or s is None:
            return 0.0
        return float(self._scores[q, s])

    def query_scores(self, query: str) -> np.ndarray:
        # Score row aligned with .samples
        q = self._queries.get(query)
        if q is None:
            return np.zeros(len(self._samples), dtype=np.float32)
        return self._scores[q]

    def sample_scores(self, sample: str) -> np.ndarray:
        # Score column aligned with .queries
        s = self._samples.get(sample)
        if s is None:
            return np.zeros(len(self._queries), dtype=np.float32)
        return self._scores[:, s]

    def max_score(self, sample: str) -> float:
        col = self.sample_scores(sample)
        return float(col.max()) if col.size else 0.0

    def __bool__(self) -> bool:
        return self._scores.size > 0

    def __eq__(self, other) -> bool:
        if not isinstance(other, KmindexQueryResult):
            return False
        return (
            self._queries == other._queries
            and self._samples == other._samples
            and np.array_equal(self._scores, other._scores)
        )

    def load_jsonl(self, file):
        # Each line is a record: {"index": ..., "query": ..., "samples": {...}}
        # The index field is ignored; repeated loads keep merging.
        pending: dict[int, list] = {}
        with open(file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                query = record["query"]
                samples = record["samples"]
                if query and samples:
                    self._add_record(query, samples, pending)

        if not pending:
            raise ValueError("Empty JSONL file")
        self._scatter(pending)

    def _add_record(self, query: str, samples: dict, pending: dict) -> None:
        # Register labels and stash the record as (cols, vals) arrays
        row = self._queries.setdefault(query, len(self._queries))
        cols = np.fromiter(
            (self._samples.setdefault(s, len(self._samples)) for s in samples),
            dtype=np.int64,
            count=len(samples),
        )
        vals = np.fromiter(samples.values(), dtype=np.float32, count=len(samples))
        pending.setdefault(row, []).append((cols, vals))

    def _scatter(self, pending: dict) -> None:
        # Grow the matrix, apply pending records (max wins on duplicates),
        # then reorder both axes by name
        grown = np.zeros((len(self._queries), len(self._samples)), dtype=np.float32)
        grown[: self._scores.shape[0], : self._scores.shape[1]] = self._scores
        for row, chunks in pending.items():
            for cols, vals in chunks:
                np.maximum.at(grown[row], cols, vals)
        q_order = sorted(self._queries)
        s_order = sorted(self._samples)
        q_idx = np.fromiter((self._queries[q] for q in q_order), dtype=np.int64)
        s_idx = np.fromiter((self._samples[s] for s in s_order), dtype=np.int64)
        self._scores = grown[np.ix_(q_idx, s_idx)] if grown.size else grown
        self._queries = {q: i for i, q in enumerate(q_order)}
        self._samples = {s: i for i, s in enumerate(s_order)}

    def _mask(self, block: np.ndarray, threshold: float) -> np.ndarray:
        # Visible cells: above threshold and an actual hit (0 = absent)
        return (block >= threshold) & (block > 0)

    def _filtered_query(self, query: str, threshold: float) -> dict:
        row = self._scores[self._queries[query]]
        names = self.samples
        visible = np.nonzero(self._mask(row, threshold))[0]
        return {names[c]: round(float(row[c]), 3) for c in visible}

    def _markdown_lines(
        self, sample_names: list[str], block: np.ndarray, threshold: float
    ) -> list[str]:
        q_names = self.queries
        q_w = max([len("Query")] + [len(q) for q in q_names])
        s_ws = [max(len(s), len("0.000")) for s in sample_names]
        mask = self._mask(block, threshold)
        lines = [
            f"| {'Query':<{q_w}} | "
            + " | ".join(f"{s:<{w}}" for s, w in zip(sample_names, s_ws))
            + " |",
            f"| {'-' * q_w} | " + " | ".join("-" * w for w in s_ws) + " |",
        ]
        for r, query in enumerate(q_names):
            cells = [
                f"{block[r, c]:.3f}".ljust(w) if mask[r, c] else " " * w
                for c, w in enumerate(s_ws)
            ]
            lines.append(f"| {query:<{q_w}} | " + " | ".join(cells) + " |")
        lines.append("")
        return lines

    def _html_document(
        self, sample_names: list[str], block: np.ndarray, threshold: float
    ) -> str:
        mask = self._mask(block, threshold)
        matrix_header = "".join(f"<th>{s}</th>" for s in sample_names)
        matrix_html = "\n".join(
            f"        <tr><td>{query}</td>"
            + "".join(
                f"<td>{block[r, c]:.3f}</td>" if mask[r, c] else "<td></td>"
                for c in range(block.shape[1])
            )
            + "</tr>"
            for r, query in enumerate(self.queries)
        )
        body = (
            f"    <h2>Score matrix</h2>\n"
            f"    <table>\n"
            f"        <tr><th>Query</th>{matrix_header}</tr>\n"
            f"{matrix_html}\n"
            f"    </table>"
        )
        return (
            f"<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
            f"    <meta charset='UTF-8'>\n"
            f"    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
            f"    <title>kmindex Results</title>\n"
            f"    <style>\n"
            f"        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}\n"
            f"        h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-top: 30px; }}\n"
            f"        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}\n"
            f"        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}\n"
            f"        th {{ background-color: #3498db; color: white; font-weight: bold; position: sticky; top: 0; }}\n"
            f"        tr:hover {{ background-color: #f5f5f5; }}\n"
            f"        tr:nth-child(even) {{ background-color: #f9f9f9; }}\n"
            f"    </style>\n</head>\n<body>\n"
            f"{body}\n"
            f"</body>\n</html>"
        )

    def _tsv_lines(self, threshold: float) -> Iterable[str]:
        yield "\t".join(["query"] + self.samples) + "\n"
        mask = self._mask(self._scores, threshold)
        for query, r in self._queries.items():
            cells = [
                f"{self._scores[r, c]:.3f}" if mask[r, c] else ""
                for c in range(self._scores.shape[1])
            ]
            yield "\t".join([query] + cells) + "\n"

    def generate_markdown(self, threshold: float = 0.0) -> str:
        return "\n".join(self._markdown_lines(self.samples, self._scores, threshold))

    def generate_html(self, threshold: float = 0.0) -> str:
        return self._html_document(self.samples, self._scores, threshold)

    def generate_tsv(self, threshold: float = 0.0) -> str:
        return "".join(self._tsv_lines(threshold))

    def generate_json(self, threshold: float = 0.0) -> str:
        filtered = {q: self._filtered_query(q, threshold) for q in self._queries}
        return json.dumps(filtered, indent=2)

    def generate_yaml(self, threshold: float = 0.0) -> str:
        filtered = {q: self._filtered_query(q, threshold) for q in self._queries}
        return yaml.dump(filtered, default_flow_style=False, sort_keys=False)

    def _check_format(self, format: str) -> str:
        key = format.lower()
        if key not in self._CONVERTERS:
            raise ValueError(
                f"Unsupported output format: {format!r}. Use: {', '.join(self._CONVERTERS)}"
            )
        return key

    def convert(self, format: str, threshold: float = 0.01) -> str:
        key = self._check_format(format)
        return getattr(self, self._CONVERTERS[key])(threshold)

    def write(
        self, path: str, format: str, threshold: float = 0.01, max_cols: int = 1000
    ) -> list[str]:
        """Write converted results to file(s) without building giant strings.

        tsv/json/yaml stream to a single file. md/html wider than max_cols
        samples are split column-wise into stem_partNNN files.

        Returns the list of written paths.
        """
        key = self._check_format(format)
        if key == "tsv":
            with open(path, "w") as f:
                f.writelines(self._tsv_lines(threshold))
            return [path]
        if key == "json":
            with open(path, "w") as f:
                f.write("{")
                for i, query in enumerate(self._queries):
                    f.write(("," if i else "") + f"\n{json.dumps(query)}: ")
                    json.dump(self._filtered_query(query, threshold), f)
                f.write("\n}")
            return [path]
        if key == "yaml":
            with open(path, "w") as f:
                for query in self._queries:
                    yaml.dump(
                        {query: self._filtered_query(query, threshold)},
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                    )
            return [path]

        # md / html: chunk sample columns into multiple files if too wide
        samples = self.samples
        if len(samples) <= max_cols:
            with open(path, "w") as f:
                f.write(self.convert(key, threshold))
            return [path]
        stem, ext = os.path.splitext(path)
        paths = []
        for part, start in enumerate(range(0, len(samples), max_cols), 1):
            names = samples[start : start + max_cols]
            block = self._scores[:, start : start + max_cols]
            content = (
                "\n".join(self._markdown_lines(names, block, threshold))
                if key == "md"
                else self._html_document(names, block, threshold)
            )
            part_path = f"{stem}_part{part:03d}{ext}"
            with open(part_path, "w") as f:
                f.write(content)
            paths.append(part_path)
        return paths


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
        result_dir = os.path.join(output_dir, "result")
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
                    print(f"Could not read result from {fpath}: {e}")

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
                            fout.write(fin.read())
                logger.info(f"Batching {len(resolved)} file(s) into a single query...")
                result = self._run_single(batch_path, total=1, idx=1)
                all_results.append(result)
            else:
                total = len(resolved)
                for idx, qfile in enumerate(resolved, 1):
                    try:
                        result = self._run_single(qfile, total=total, idx=idx)
                        all_results.append(result)
                    except Exception as e:
                        logger.error(f"[{os.path.basename(qfile)}] {e}")
                        errors.append(f"{os.path.basename(qfile)}: {e}")
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
        result_dir = os.path.join(query_output, "result")
        logger.info(f"Time: {elapsed:.2f}s")
        logger.info(f"Results: {result_dir}")

        if cfg.output_format != "json":
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
        if not merged:
            return
        if self._config.print_output:
            sys.stdout.write(f"{merged.convert(format=fmt, threshold=threshold)}\n")
        else:
            out_file = os.path.join(result_dir, f"results.{fmt}")
            for written in merged.write(out_file, fmt, threshold):
                logger.debug(f"Converted: {written}")
