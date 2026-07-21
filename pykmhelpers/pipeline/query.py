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


class KmindexQueryResult:
    _CONVERTERS: dict[str, str] = {
        "md": "generate_markdown",
        "html": "generate_html",
        "csv": "generate_csv",
        "json": "generate_json",
        "yaml": "generate_yaml",
    }

    def __init__(self, file: str) -> None:
        self._result = {}
        if file:
            self.load_json(file)

    @property
    def result(self):
        return self._result

    def get_index_result(self, index_id) -> dict:
        return self.result.get(index_id, dict)

    def __eq__(self, other) -> bool:
        if not isinstance(other, KmindexQueryResult):
            return False
        return self._result == other._result

    def load_json(self, file):
        with open(file, "r") as f:
            self._result = json.load(f)

        if not self._result:
            raise ValueError("Empty JSON file")

        self.index_name = list(self._result.keys())[0]
        self.queries = self._result[self.index_name]

    def max_score(self, sample):
        max_score = 0
        for _, samples in self.queries.items():
            max_score = max(max_score, samples.get(sample, 0))
        return max_score

    def _filtered_sorted_samples(
        self, samples: dict, threshold: float
    ) -> list[tuple[str, float]]:
        return sorted(
            [(s, sc) for s, sc in samples.items() if sc >= threshold],
            key=lambda x: x[1],
            reverse=True,
        )

    def generate_markdown(self, threshold: float = 0.0) -> str:
        lines = []
        for query_name, samples in self.queries.items():
            lines.append(
                f"## Query {query_name} on {self.index_name} - Filter scores ≥ {threshold}\n"
            )
            sorted_samples = self._filtered_sorted_samples(samples, threshold)
            col_w = max((len(s) for s, _ in sorted_samples), default=len("Sample"))
            col_w = max(col_w, len("Sample"))
            lines.append(f"| {'Sample':<{col_w}} | Score |")
            lines.append(f"| {'-' * col_w} | ----- |")
            for sample, score in sorted_samples:
                lines.append(f"| {sample:<{col_w}} | {score:.3f} |")
            lines.append("")
        return "\n".join(lines)

    def generate_html(self, threshold: float = 0.0) -> str:
        rows = []
        for query_name, samples in self.queries.items():
            sorted_samples = self._filtered_sorted_samples(samples, threshold)
            row_html = "\n".join(
                f"        <tr><td>{s}</td><td>{sc:.3f}</td></tr>"
                for s, sc in sorted_samples
            )
            rows.append(
                f"    <details open><summary>"
                f"<h2>Query {query_name} on {self.index_name} - Filter scores ≥ {threshold}</h2>"
                f"</summary>\n"
                f"    <table>\n"
                f"        <tr><th>Sample</th><th>Score</th></tr>\n"
                f"{row_html}\n"
                f"    </table></details>"
            )
        body = "\n".join(rows)
        return (
            f"<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
            f"    <meta charset='UTF-8'>\n"
            f"    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
            f"    <title>kmindex Results - {self.index_name}</title>\n"
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

    def generate_csv(self, threshold: float = 0.0) -> str:
        lines = ["query,sample,score"]
        for query_name, samples in self.queries.items():
            for sample, score in self._filtered_sorted_samples(samples, threshold):
                lines.append(f"{query_name},{sample},{score:.3f}")
        return "\n".join(lines)

    def generate_json(self, threshold: float = 0.0) -> str:
        filtered = {
            self.index_name: {
                query_name: {s: sc for s, sc in samples.items() if sc >= threshold}
                for query_name, samples in self.queries.items()
            }
        }
        return json.dumps(filtered, indent=2)

    def generate_yaml(self, threshold: float = 0.0) -> str:
        filtered = {
            self.index_name: {
                query_name: {
                    s: round(sc, 3) for s, sc in samples.items() if sc >= threshold
                }
                for query_name, samples in self.queries.items()
            }
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
        )

        # Save result to info.yaml
        info_file = os.path.join(output_dir, "info.yaml")
        with open(info_file, "w") as f:
            yaml.safe_dump(output, f)

        result = []

        for f in os.listdir(result_dir):
            fpath = os.path.join(result_dir, f)
            if os.path.isfile(fpath) and f.endswith(".json"):
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
        output_format: Output format for result conversion (``json``, ``yaml``, ``md``, ``html``, ``csv``).
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
        for fname in os.listdir(result_dir):
            if not fname.endswith(".json"):
                continue
            json_path = os.path.join(result_dir, fname)
            try:
                result = KmindexQueryResult(json_path)
                converted = result.convert(format=fmt, threshold=threshold)
                if self._config.print_output:
                    sys.stdout.write(converted)
                else:
                    stem = os.path.splitext(fname)[0]
                    out_file = os.path.join(result_dir, f"{stem}.{fmt}")
                    with open(out_file, "w") as f:
                        f.write(converted)
                    logger.debug(f"Converted: {out_file}")
            except Exception as e:
                logger.warning(f"Failed to convert {fname}: {e}")
