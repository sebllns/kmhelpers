import logging
import platform
import sys
from collections.abc import Iterable

import pykmhelpers
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.log import Log
from pykmhelpers.pipeline.index_ops.types import (
    ApplyInputType,
    ApplyMode,
    ApplyResult,
    ApplyStatus,
)

logger = logging.getLogger(__name__)

FAILED = ApplyStatus.FAILED.value
SUCCESS = ApplyStatus.SUCCESS.value
PARTIAL = ApplyStatus.PARTIAL.value
NONE = ApplyStatus.NONE.value


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


class RunReport:
    """Accumulates the outcome of one ``IndexOps.run`` into an ``ApplyResult``."""

    def __init__(self, path: str, mode: ApplyMode) -> None:
        wrapper = KmindexWrapper(dry_run=False)
        self.result = ApplyResult(
            status=ApplyStatus.NONE,
            input_type=ApplyInputType.UNKNOWN,
            mode=mode,
            details={
                "input_file": path,
                "kmindex": {
                    "version": wrapper.kmindex_version(),
                    "path": wrapper.which,
                },
                "kmhelpers": {
                    "version": pykmhelpers.__version__,
                    "path": sys.argv[0],
                },
                "system": {
                    "os": platform.system(),
                    "os_version": platform.version(),
                },
                "span": {},
                "run": {},
            },
        )

    @property
    def _runs(self) -> dict:
        runs: dict = self.result.details["run"]
        return runs

    def record(
        self,
        name: str,
        status: ApplyStatus,
        error: str | None = None,
        issues: list[str] | None = None,
    ) -> None:
        entry: dict = {"result": status.value}
        if issues:
            entry["issues"] = issues
        if error:
            entry["error"] = error
        self._runs[name] = entry

    def add_span_stats(self, span: int, sample_count: int, byte_count: int) -> None:
        stats = self.result.details["span"].setdefault(
            span, {"sample_count": 0, "bytes": 0, "size_str": "0B"}
        )
        stats["sample_count"] += sample_count
        stats["bytes"] += byte_count
        stats["size_str"] = str(ByteCounter.auto(stats["bytes"]))

    def fold_merge(self, target: str, parts: list[str]) -> None:
        """Move the entries of ``parts`` under ``target`` and derive its status."""
        entry: dict = {"result": SUCCESS}
        for part in parts:
            entry[part] = self._runs.pop(part, {"result": NONE})
        part_results = [v.get("result") for v in entry.values() if isinstance(v, dict)]
        entry["result"] = merge_status(part_results).value
        self._runs[target] = entry

    def fail(self, e: Exception, msg: str, key: str | None, abort: bool) -> bool:
        """Log an error and record it under ``key``. Returns True if the run must stop."""
        Log.handle_exception(logger, e, msg)
        if key:
            self.record(key, ApplyStatus.FAILED, Log.format_exception(e))
        self.result.status = ApplyStatus.FAILED if abort else ApplyStatus.PARTIAL
        return abort

    def finish(self) -> ApplyResult:
        self.result.status = run_status(
            v.get("result") for v in self._runs.values() if isinstance(v, dict)
        )
        return self.result
