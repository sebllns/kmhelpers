"""What ``kmhelpers manage clean`` may remove from a build directory (the registry).

- the kmtricks build intermediates left in published shards: neither kmindex
  (query, register, merge) nor kmhelpers reads them once the run is built;
- ``assets/<session>/`` of the finished sessions: every shard published, no job left;
- the logs and reports in ``logs/``; the stats (``stats.yaml``,
  ``<run>.stats.json``) are kept.
"""

import glob
import os

import yaml

from pykmhelpers.pipeline.index_ops.paths import STATS_FILE, BuildPaths
from pykmhelpers.pipeline.index_ops.report import dir_bytes
from pykmhelpers.pipeline.index_ops.status import BuildState, active_jobs

# Folders of a kmtricks run that a published index does not need. Kept:
# matrices/, hash.info, repartition_gatb/, options.txt, kmtricks.fof,
# build_infos.txt (kmindex query), config_gatb/ (kmindex merge),
# run_infos.txt and fpr/ (kmhelpers stats)
BUILD_LEFTOVERS = (
    "superkmers",
    "counts",
    "minimizers",
    "partition_infos",
    "merge_infos",
    "histograms",
    "filters",
    "howde_index",
)


def path_bytes(path: str) -> int:
    if os.path.isdir(path) and not os.path.islink(path):
        return dir_bytes(path)
    try:
        return os.lstat(path).st_size
    except OSError:
        return 0


def shard_leftovers(registry, shards: list[str]) -> list[str]:
    """Build intermediates present in the folders of ``shards``; a symlinked
    shard (``manage add``) is followed."""
    found = []
    for shard in shards:
        root = os.path.realpath(registry.get_index_path(shard))
        for name in BUILD_LEFTOVERS:
            path = os.path.join(root, name)
            if os.path.isdir(path):
                found.append(path)
    return found


def sessions(build_dir: str) -> dict[str, BuildState]:
    """One state per session with a plan, ``assets/<session>/plan.yaml``."""
    states = {}
    for plan_file in sorted(glob.glob(os.path.join(glob.escape(build_dir), "assets", "*", "plan.yaml"))):
        session = os.path.basename(os.path.dirname(plan_file))
        try:
            with open(plan_file) as f:
                plan = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            plan = {}
        plan.setdefault("tasks", {})
        states[session] = BuildState(plan, BuildPaths(build_dir, session))
    return states


def finished_assets(build_dir: str) -> tuple[list[str], dict[str, str]]:
    """``assets/<session>/`` folders that can go, and the kept ones with why.

    A session is finished when no job of its plan is queued or running and
    every one of its shards holds the samples of its task. A folder without
    a plan is kept: it may be a plan being written.
    """
    removable, kept = [], {}
    states = sessions(build_dir)
    for session, state in states.items():
        active = active_jobs(state)
        if active:
            kept[session] = f"{len(active)} job(s) queued or running"
            continue
        pending = [t["shard"] for t in state.tasks.values() if not state.task_done(t)]
        if pending:
            kept[session] = f"not published: {', '.join(sorted(set(pending)))}"
            continue
        removable.append(state.paths.assets)
    for folder in sorted(glob.glob(os.path.join(glob.escape(build_dir), "assets", "*"))):
        name = os.path.basename(folder)
        if os.path.isdir(folder) and name not in states:
            kept[name] = "no plan.yaml"
    return removable, kept


def active_sessions(build_dir: str) -> list[str]:
    """Sessions with a job still queued or running."""
    return [s for s, state in sessions(build_dir).items() if active_jobs(state)]


def log_files(build_dir: str) -> list[str]:
    """Logs and reports of ``logs/``: ``<shard>/*.log``, ``*.log.prev``,
    ``slurm/`` and the ``kmhelpers_*.yaml`` reports. The stats stay."""
    logs = os.path.join(build_dir, "logs")
    if not os.path.isdir(logs):
        return []
    found = sorted(glob.glob(os.path.join(glob.escape(logs), "kmhelpers_*.yaml")))
    slurm = os.path.join(logs, "slurm")
    if os.path.isdir(slurm):
        found.append(slurm)
    for entry in sorted(os.listdir(logs)):
        folder = os.path.join(logs, entry)
        if entry == "slurm" or not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name == STATS_FILE or name.endswith(".stats.json"):
                continue
            if name.endswith(".log") or name.endswith(".log.prev"):
                found.append(os.path.join(folder, name))
    return found
