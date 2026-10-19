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

from pykmhelpers.core.constants import DATA_EXT_ALL, strip_data_ext
from pykmhelpers.core.kmindex_paths import get_json_path
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.sequence import Sequence
from pykmhelpers.core.utils import Toolbox, detect_compression, open_decompressed
from pykmhelpers.pipeline.query_result import KmindexQueryResult

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
    ) -> list[KmindexQueryResult]:
        """Run a query against the kmindex registry.

        Args:
            registry_path (str): Path to the kmindex registry.
            output_dir (str): Output directory for query results.
            index_ids (list[str]): Index IDs to query against; empty list queries all.
            z (int): Z-value (error rate parameter) for kmindex.
            threshold (float): Minimum score threshold for reported hits.
            single_query (str, optional): Query identifier; treats all sequences
                as one query.
            aggregate (bool): Whether to aggregate batch results into a single file.
            threads (int): Number of threads to use.
            fast (bool): Enable fast mode (disabled automatically when
                `is_compressed` is True).
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

        result: list[KmindexQueryResult] = []

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
            ``tsv``), ``None`` keeps only the raw kmindex results.
        export: Human report written beside the data (``md``, ``html``),
            ``None`` for none. Requires ``output_format``.
        timestamp: Append a ``YYYYmmdd_HHMMSS`` suffix to each per-query output
            directory.
        on_existing: Behaviour when the output directory already exists
            (``skip``, ``fail``, ``delete``, ``new-name``).
        parallel: Parallelisation strategy passed to kmindex (``seq`` or ``sub``).
            Forced to ``sub`` when ``compressed`` is ``True``.
        force: Skip confirmation prompts (e.g. when ``on_existing="delete"``).
        print_output: Write the converted data to stdout instead of saving it
            to file. Reports are always written to files.
        keep_query: Copy each query file into its output directory.
        stats: Write sequence_stats.tsv and sample_stats.tsv.
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
    stats: bool = True
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
                "--compressed requires sub parallelization strategy; "
                "forcing parallel=sub"
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
                    plain = os.path.join(tmp_dir, name[: name.rfind(".")])
                    with open_decompressed(qfile) as fin, open(plain, "wb") as fout:
                        shutil.copyfileobj(fin, fout)
                    qfile = plain
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

        resolved = self._resolve_existing(query_output, stem)
        if resolved is None:
            return []
        query_output = resolved

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
        if files and self._config.stats and not self._config.print_output:
            out_dir = os.path.dirname(result_dir)
            for name, content in (
                ("sequence_stats.tsv", merged.generate_sequence_stats_tsv(threshold)),
                ("sample_stats.tsv", merged.generate_sample_stats_tsv(threshold)),
            ):
                with open(os.path.join(out_dir, name), "w") as f:
                    f.write(content)
            logger.info(
                f"Statistics: {os.path.join(out_dir, 'sequence_stats.tsv')}, "
                "sample_stats.tsv"
            )

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
        assert cfg.export is not None
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
