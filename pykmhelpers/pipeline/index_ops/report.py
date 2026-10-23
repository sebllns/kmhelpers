import logging
import os
import platform
import sys
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Optional

import yaml

import pykmhelpers
from pykmhelpers.core.build_params import _resolve_limits
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.constants import KMHELPERS_COMMIT
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.log import Log
from pykmhelpers.core.resources import get_ulimit
from pykmhelpers.pipeline.index_ops.merging import MergeLimits
from pykmhelpers.pipeline.index_ops.types import (
    ApplyInputType,
    ApplyMode,
    ApplyResult,
    ApplyStatus,
    IndexOpsConfig,
)

logger = logging.getLogger(__name__)

FAILED = ApplyStatus.FAILED.value
SUCCESS = ApplyStatus.SUCCESS.value
PARTIAL = ApplyStatus.PARTIAL.value
NONE = ApplyStatus.NONE.value
RUNNING = "RUNNING"  # status written while the run is not finished

_COMMANDS = {
    ApplyMode.DRY_RUN: "dry-run",
    ApplyMode.PLAN: "plan",
    ApplyMode.APPLY: "apply",
    ApplyMode.APPLY_SHOW_PROGRESS: "apply",
}

_SLURM_ENV = {
    "job_id": "SLURM_JOB_ID",
    "array_task_id": "SLURM_ARRAY_TASK_ID",
    "job_name": "SLURM_JOB_NAME",
    "partition": "SLURM_JOB_PARTITION",
    "node": "SLURMD_NODENAME",
    "cpus_per_task": "SLURM_CPUS_PER_TASK",
    "mem_per_node_mb": "SLURM_MEM_PER_NODE",
}


def indent_prefix(log: logging.Logger) -> str:
    return "  └── " if log.isEnabledFor(logging.INFO) else ""


def run_status(results: Iterable[str | None]) -> ApplyStatus:
    """Overall status of a run from its per-item results."""
    entries = list(results)
    if not entries:
        return ApplyStatus.NONE
    has_failed = FAILED in entries
    has_ok = SUCCESS in entries
    if PARTIAL in entries or (has_failed and has_ok):
        return ApplyStatus.PARTIAL
    if has_failed:
        return ApplyStatus.FAILED
    if has_ok:
        return ApplyStatus.SUCCESS
    return ApplyStatus.NONE


def merge_status(results: Iterable[str | None]) -> ApplyStatus:
    """Status of a merge target from the results of its parts.

    Unlike ``run_status``, a single failed part makes the merge PARTIAL,
    and a merge with no recorded part counts as SUCCESS.
    """
    entries = list(results)
    if entries and all(r == FAILED for r in entries):
        return ApplyStatus.FAILED
    if FAILED in entries:
        return ApplyStatus.PARTIAL
    if entries and all(r == NONE for r in entries):
        return ApplyStatus.NONE
    return ApplyStatus.SUCCESS


def _size(n_bytes: int) -> str:
    return str(ByteCounter.auto(int(n_bytes)))


def dir_bytes(path: str) -> int:
    """Bytes of the files under ``path`` (followed when it is a link)."""
    total = 0
    for root, _, files in os.walk(os.path.realpath(path)):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def _system() -> dict:
    info: dict = {
        "host": platform.node(),
        "os": platform.system(),
        "kernel": platform.release(),
        "cpus": os.cpu_count(),
    }
    slurm = {k: os.environ[v] for k, v in _SLURM_ENV.items() if os.environ.get(v)}
    if slurm:
        info["slurm"] = slurm
    return info


def _kmhelpers() -> dict:
    # The kmhelpers of this installation, as the executor puts it first in PATH
    path = os.path.join(os.path.dirname(sys.executable), "kmhelpers")
    return {
        "version": pykmhelpers.__version__,
        # git commit of the installed source tree, UNKNOWN outside git
        "commit": KMHELPERS_COMMIT,
        "path": path if os.path.exists(path) else sys.argv[0],
    }


def _limits(config: IndexOpsConfig) -> dict:
    """Resource limits sizing uses: from ``--limits``, else detected."""
    try:
        ram, files, threads, _ = _resolve_limits(
            config.limits or "{}", config.safety_margin
        )
        maps = MergeLimits.resolve(config.limits, config.safety_margin).maps
        soft, hard = get_ulimit()
    except Exception as e:
        logger.debug(f"Could not resolve limits for the report: {e}")
        return {}
    if config.kmindex_threads:
        source = "--threads"
    else:
        source = "--limits" if config.limits else "auto"
    return {
        "source": source,
        "ram": _size(ram),
        "ram_bytes": int(ram),
        "files": int(files),
        "files_soft": soft,
        "files_hard": hard,
        "threads": int(config.kmindex_threads or threads),
        "max_map_count": maps,
        "safety_margin": config.safety_margin,
        "max_chunks": config.max_chunks,
        "chunk_budget": config.chunk_budget,
    }


class RunReport:
    """Accumulates the outcome of one ``IndexOps.run`` into an ``ApplyResult``.

    ``details`` is organised by shard (``shards``): one entry per part, folded
    under its shard once published. With ``dump_path``, ``dump`` writes it as
    YAML, so a run still going or killed leaves its report so far.
    """

    def __init__(
        self,
        path: str,
        mode: ApplyMode,
        config: Optional[IndexOpsConfig] = None,
        dump_path: Optional[str] = None,
    ) -> None:
        wrapper = KmindexWrapper(dry_run=False)
        self._dump_path = dump_path
        self._start = time.monotonic()
        self.result = ApplyResult(
            status=ApplyStatus.NONE,
            input_type=ApplyInputType.UNKNOWN,
            mode=mode,
            details={
                "summary": {
                    "command": _COMMANDS[mode],
                    "status": RUNNING,
                    "input_type": ApplyInputType.UNKNOWN.value,
                    "started": datetime.now().isoformat(timespec="seconds"),
                },
                "input_file": path,
                "build_dir": {},
                "kmindex": {
                    "version": wrapper.kmindex_version(),
                    "path": wrapper.which,
                },
                "kmhelpers": _kmhelpers(),
                "system": _system(),
                "limits": _limits(config) if config else {},
                "shards": {},
            },
        )
        self._spans: dict = {}
        self._disk: dict[str, int] = {}
        if config:
            self.set_build_dir(config.workdir)

    @property
    def _shards(self) -> dict:
        shards: dict = self.result.details["shards"]
        return shards

    @property
    def _summary(self) -> dict:
        summary: dict = self.result.details["summary"]
        return summary

    def set_build_dir(self, build_dir: str, assets: Optional[str] = None) -> None:
        entry = {"path": build_dir, "logs": os.path.join(build_dir, "logs")}
        if assets:
            entry["assets"] = assets
        self.result.details["build_dir"] = entry

    def set_input_type(self, input_type: ApplyInputType) -> None:
        self.result.input_type = input_type
        self._summary["input_type"] = input_type.value

    def _entry(self, name: str) -> dict:
        entry: dict = self._shards.setdefault(name, {"result": NONE})
        return entry

    def record(
        self,
        name: str,
        status: ApplyStatus,
        error: str | None = None,
        issues: list[str] | None = None,
    ) -> None:
        """Set the result of ``name``, keeping what is already recorded for it."""
        entry = self._entry(name)
        entry["result"] = status.value
        if issues:
            entry["issues"] = issues
        if error:
            entry["error"] = error

    def record_params(self, name: str, definition, params, sample_count: int) -> None:
        """Parameters ``name`` is built with (``definition`` an ``IndexDefinition``,
        ``params`` its ``BuildParams``)."""
        entry = self._entry(name)
        entry["span"] = definition.span
        entry["samples"] = sample_count
        if sample_count != definition.sample_count:
            entry["planned_samples"] = definition.sample_count
        entry["params"] = {
            "threads": params.threads,
            "partitions": params.partitions,
            "partitions_source": params.partitions_source,
            "minim_size": params.minim_size,
            "chunk_size": params.chunk_size,
            "kmer_size": definition.kmer_size,
            "abundance_min": definition.abundance_min,
            "bf_size": definition.bf_size,
            "bitw": definition.bitw,
            "kmer_ratio": definition.kmer_ratio,
        }
        entry["est_size"] = str(definition.get_stored_size())

    def record_script(self, name: str, script: str) -> None:
        self._entry(name)["script"] = script

    def record_runs(self, name: str, runs: dict[str, dict]) -> None:
        """kmtricks runs of ``name``: run name -> what the executor knows of it."""
        threads = self._entry(name).get("params", {}).get("threads")
        ram = self.result.details["limits"].get("ram_bytes")
        entries = self._entry(name).setdefault("runs", {})
        for run, info in runs.items():
            info = dict(info)
            if "peak_rss_mb" in info:
                peak = info.pop("peak_rss_mb") * 1024 * 1024
                info["peak_rss"] = _size(peak)
                if ram:
                    info["ram_limit_use"] = round(peak / ram, 3)
            if threads and "max_cpu_pct" in info:
                info["threads"] = threads
                info["cpu_efficiency"] = round(info["max_cpu_pct"] / (100 * threads), 2)
            entries[run] = info

    def record_merge(self, target: str, info: dict) -> None:
        """How ``target`` was published (``IndexExecutor.publish_details``)."""
        info = dict(info)
        if "disk_bytes" in info:
            self._disk[target] = info["disk_bytes"]
            info["disk_size"] = _size(info.pop("disk_bytes"))
        self._entry(target).update(info)

    def add_span_stats(self, span: int, sample_count: int, byte_count: int) -> None:
        stats = self._spans.setdefault(span, {"shards": 0, "samples": 0, "bytes": 0})
        stats["shards"] += 1
        stats["samples"] += sample_count
        stats["bytes"] += byte_count

    def result_of(self, name: str) -> str | None:
        """Recorded result of ``name``, if any."""
        result: str | None = self._shards.get(name, {}).get("result")
        return result

    def fold_merge(self, target: str, parts: list[str]) -> None:
        """Move the entries of ``parts`` under ``target`` and derive its status."""
        entry: dict = {"result": SUCCESS}
        for part in parts:
            entry[part] = self._shards.pop(part, {"result": NONE})
        # publish details recorded before the fold stay on the target
        published = self._shards.pop(target, {})
        entry.update({k: v for k, v in published.items() if k != "result"})
        part_results = [v.get("result") for v in self._parts(entry)]
        entry["result"] = merge_status(part_results).value
        self._shards[target] = entry

    def fail(self, e: Exception, msg: str, key: str | None, abort: bool) -> bool:
        """Log an error and record it under ``key``. Returns True if the run must stop."""
        Log.handle_exception(logger, e, msg)
        if key:
            self.record(key, ApplyStatus.FAILED, Log.format_exception(e))
        self.result.status = ApplyStatus.FAILED if abort else ApplyStatus.PARTIAL
        self.dump()
        return abort

    def finish(self) -> ApplyResult:
        self.result.status = run_status(
            v.get("result") for v in self._shards.values() if isinstance(v, dict)
        )
        return self.result

    def close(self) -> ApplyResult:
        """Fill the summary with the final status, then dump the report."""
        self._fill_summary(final=True)
        self.dump()
        return self.result

    def dump(self) -> None:
        """Write the report to ``dump_path`` (no-op without one)."""
        if not self._dump_path:
            return
        self._fill_summary(final=False)
        try:
            with open(self._dump_path, "w") as f:
                yaml.dump(
                    self.result.details, f, default_flow_style=False, sort_keys=False
                )
        except OSError as e:
            logger.warning(f"Could not write the report {self._dump_path}: {e}")

    # ---
    # PRIVATE METHODS

    @staticmethod
    def _parts(entry: dict) -> list[dict]:
        """Part entries nested in a shard entry (dicts holding a ``result``)."""
        return [v for v in entry.values() if isinstance(v, dict) and "result" in v]

    def _fill_summary(self, final: bool) -> None:
        summary = self._summary
        if final:
            summary["status"] = self.result.status.value
            summary["finished"] = datetime.now().isoformat(timespec="seconds")
            summary["duration_s"] = round(time.monotonic() - self._start, 1)
        else:
            summary["duration_s"] = round(time.monotonic() - self._start, 1)

        counts = {s.value: 0 for s in ApplyStatus}
        runs = 0
        for entry in self._shards.values():
            result = entry.get("result", NONE)
            counts[result] = counts.get(result, 0) + 1
            for part in [entry] + self._parts(entry):
                runs += len(part.get("runs", {}))
        est = sum(s["bytes"] for s in self._spans.values())
        summary["counts"] = counts
        summary["totals"] = {
            "shards": len(self._shards),
            "samples": sum(s["samples"] for s in self._spans.values()),
            "runs": runs,
            "est_size": _size(est),
        }
        if self._disk:
            summary["totals"]["disk_size"] = _size(sum(self._disk.values()))
        summary["spans"] = {
            span: {
                "shards": s["shards"],
                "samples": s["samples"],
                "est_size": _size(s["bytes"]),
            }
            for span, s in sorted(self._spans.items())
        }
        # times next to the status, whatever was filled first
        order = ["command", "status", "input_type", "started", "finished", "duration_s"]
        ordered = {k: summary.pop(k) for k in order if k in summary}
        self.result.details["summary"] = {**ordered, **summary}
