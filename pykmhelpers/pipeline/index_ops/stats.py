"""Stats of the kmtricks runs and of the shards they are published in.

Each chunk script writes ``logs/<shard>/<run>.stats.json`` once its run is built
(``write_run_stats``), before it removes the superkmers of the run, so the disk
of the run is its peak. ``publish.sh`` folds them into ``logs/<shard>/stats.yaml``
(``write_shard_stats``) once the shard is published and checked; the stats of
earlier sessions are kept, so the summary covers the whole shard.

The FP rate of a sample is the one kmtricks estimates for each of its Bloom
filters (``fpr/partition_<p>.txt``, one line per sample in ``kmtricks.fof``
order), averaged over the partitions. It is the FP rate of one k-mer, before
findere (z).
"""

import glob
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

import yaml

from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.kmindex_layout import load_options_file
from pykmhelpers.pipeline.index_ops.paths import STATS_FILE
from pykmhelpers.pipeline.index_ops.report import dir_bytes
from pykmhelpers.pipeline.index_ops.status import _atomic_write

logger = logging.getLogger(__name__)

# Samples above this FP rate are listed in the shard stats
FPR_WARN = 0.01

_TIME = re.compile(r"^Time: ([\d.]+) seconds", re.M)
_MEMORY = re.compile(r"^Memory: ([\d.]+) ?MB", re.M)


def _size(n_bytes: float) -> str:
    return str(ByteCounter.auto(int(n_bytes)))


def fof_order(path: str) -> list[str]:
    """Sample names of a kmtricks.fof, in file order."""
    with open(path) as f:
        return [n for n in (line.split(":", 1)[0].strip() for line in f) if n]


def sample_fpr(run_dir: str, names: list[str]) -> dict[str, float]:
    """FP rate of each sample of ``run_dir``: mean over its partitions."""
    sums = [0.0] * len(names)
    count = 0
    for path in glob.glob(os.path.join(glob.escape(run_dir), "fpr", "partition_*.txt")):
        with open(path) as f:
            values = [float(v) for v in f if v.strip()]
        if len(values) != len(names):
            raise ValueError(f"{path}: {len(values)} values for {len(names)} samples")
        sums = [s + v for s, v in zip(sums, values)]
        count += 1
    if not count:
        return {}
    return {n: round(s / count, 6) for n, s in zip(names, sums)}


def fpr_summary(fpr: dict[str, float]) -> dict:
    """Mean and max FP rate, and the samples above ``FPR_WARN``."""
    if not fpr:
        return {}
    worst = max(fpr, key=lambda n: fpr[n])
    return {
        "fpr_mean": round(sum(fpr.values()) / len(fpr), 6),
        "fpr_max": fpr[worst],
        "fpr_max_sample": worst,
        "fpr_above_1pct": sorted(n for n, v in fpr.items() if v > FPR_WARN),
    }


def run_stats(run_dir: str, fpr: bool = False) -> dict:
    """Time, peak RAM, disk, samples and Bloom filter size of a complete run.

    Time and peak RAM are the ones kmtricks writes in ``run_infos.txt``. With
    ``fpr``, adds the FP rate of each sample (``fpr``) and its summary.
    """
    stats: dict = {"run": os.path.basename(os.path.normpath(run_dir)), "run_dir": run_dir}
    try:
        with open(os.path.join(run_dir, "run_infos.txt")) as f:
            infos = f.read()
    except OSError:
        infos = ""
    if m := _TIME.search(infos):
        stats["duration_s"] = float(m.group(1))
    if m := _MEMORY.search(infos):
        stats["peak_rss_mb"] = round(float(m.group(1)), 1)

    disk = dir_bytes(run_dir)
    stats["disk_bytes"] = disk
    stats["disk_size"] = _size(disk)
    names = fof_order(os.path.join(run_dir, "kmtricks.fof"))
    stats["samples"] = len(names)
    options = load_options_file(os.path.join(run_dir, "options.txt"))
    stats["bloom_size"] = options.get("bloom_size")
    matrices = glob.glob(os.path.join(glob.escape(run_dir), "matrices", "matrix_*.cmbf"))
    stats["partitions"] = len(matrices)
    bf_bytes = sum(os.path.getsize(m) for m in matrices)
    stats["bf_bytes"] = bf_bytes
    stats["bf_size"] = _size(bf_bytes)
    if fpr:
        per_sample = sample_fpr(run_dir, names)
        stats.update(fpr_summary(per_sample))
        stats["fpr"] = per_sample
    return stats


def write_run_stats(run_dir: str, out: str, fpr: bool = False) -> dict:
    """Write the stats of ``run_dir`` to ``out`` (JSON); return them.

    An existing file is kept once the superkmers of the run are removed: the
    disk of the run would no longer be its peak (a reused run).
    """
    if os.path.isfile(out) and not os.path.isdir(os.path.join(run_dir, "superkmers")):
        try:
            with open(out) as f:
                kept: dict = json.load(f)
            if kept.get("run_dir") == run_dir and (not fpr or "fpr" in kept):
                return kept
        except (OSError, ValueError):
            pass
    stats = run_stats(run_dir, fpr)
    _atomic_write(out, json.dumps(stats) + "\n")
    return stats


def _summary(sessions: dict, fpr: dict[str, float], samples: int, shard_bytes: int) -> dict:
    chunks = [c for s in sessions.values() for c in (s.get("chunks") or {}).values()]
    publishes = [s.get("publish") or {} for s in sessions.values()]
    duration = sum(c.get("duration_s") or 0 for c in chunks)
    duration += sum(p.get("duration_s") or 0 for p in publishes)
    peak_disk = max([c.get("disk_bytes") or 0 for c in chunks] + [shard_bytes])
    rss = [c["peak_rss_mb"] for c in chunks if c.get("peak_rss_mb") is not None]
    summary: dict = {
        "samples": samples,
        "chunks": len(chunks),
        "duration_s": round(duration, 1),
        "peak_rss_mb": max(rss) if rss else None,
        "peak_disk_bytes": peak_disk,
        "peak_disk_size": _size(peak_disk),
        "bloom_size": next(
            (c["bloom_size"] for c in reversed(chunks) if c.get("bloom_size")), None
        ),
        "disk_bytes": shard_bytes,
        "disk_size": _size(shard_bytes),
    }
    summary.update(fpr_summary(fpr))
    return summary


def write_shard_stats(
    out: str,
    shard: str,
    session: str,
    run_stats_files: list[str],
    publish_seconds: Optional[float],
    shard_dir: str,
) -> dict:
    """Fold the run stats of ``session`` into the stats of ``shard`` (``out``).

    The sessions already in ``out`` are kept, a session written again (a
    publish run again) is replaced. The per-sample FP rates are kept for the
    samples the shard holds.
    """
    data: dict = {}
    if os.path.isfile(out):
        try:
            with open(out) as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            logger.warning(f"Could not read {out}, writing it again: {e}")
    sessions: dict = data.get("sessions") or {}
    fpr: dict[str, float] = dict(data.get("fpr_samples") or {})

    chunks: dict = {}
    for path in run_stats_files:
        try:
            with open(path) as f:
                stats = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"No stats for a run of '{shard}' ({path}): {e}")
            continue
        fpr.update(stats.pop("fpr", None) or {})
        chunks[stats.pop("run", os.path.basename(path))] = stats
    shard_bytes = dir_bytes(shard_dir)
    publish: dict = {"disk_bytes": shard_bytes, "disk_size": _size(shard_bytes)}
    if publish_seconds is not None:
        publish["duration_s"] = round(publish_seconds, 1)
    sessions[session] = {"chunks": chunks, "publish": publish}

    fof = os.path.join(shard_dir, "kmtricks.fof")
    held = set(fof_order(fof)) if os.path.isfile(fof) else set()
    if held:
        fpr = {n: v for n, v in fpr.items() if n in held}
    samples = len(held) or sum(c.get("samples") or 0 for c in chunks.values())
    data = {
        "shard": shard,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "summary": _summary(sessions, fpr, samples, shard_bytes),
        "sessions": sessions,
    }
    if fpr:
        data["fpr_samples"] = dict(sorted(fpr.items()))
    _atomic_write(out, yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    return data


def shard_stats_path(registry: str, shard: str) -> str:
    """``stats.yaml`` of ``shard`` in the registry (build directory) ``registry``."""
    return os.path.join(registry, "logs", shard, STATS_FILE)


def load_shard_fpr(registry: str, shard: str) -> dict[str, float]:
    """Per-sample FP rates recorded for ``shard``; empty when there are none."""
    try:
        with open(shard_stats_path(registry, shard)) as f:
            return dict((yaml.safe_load(f) or {}).get("fpr_samples") or {})
    except (OSError, yaml.YAMLError, AttributeError):
        return {}
