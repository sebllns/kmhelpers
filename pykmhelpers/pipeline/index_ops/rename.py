"""Renames in a registry (``kmhelpers manage rename``).

A shard is the folder (or symlink) ``<registry>/<shard>`` and its entry in
``index.json``. kmindex stores nothing name-specific in the folder, so a
rename is the folder rename and the key of its entry: no kmindex call. Its
logs and stats, ``logs/<shard>/``, follow it.

An index ``NAME`` is the set of its shards, ``NAME_g<k>`` and
``NAME_g<k>_p<j>``; its compose layout, ``COMPOSE_DIR/NAME/layout.yaml``,
records their names and is used by the next ``compose`` of the index.
"""

import json
import logging
import os
import re
import shutil
from datetime import datetime
from typing import Optional

import yaml

from pykmhelpers.core.file_lock import locked, remove_if_free, replace_atomically
from pykmhelpers.pipeline.composer import LAYOUT_FILE, layout_lock
from pykmhelpers.pipeline.index_ops.clean import sessions
from pykmhelpers.pipeline.index_ops.paths import STATS_FILE, BuildPaths, check_index_name
from pykmhelpers.pipeline.index_ops.status import active_jobs

logger = logging.getLogger(__name__)


def index_shards(names: list[str], index: str) -> list[str]:
    """Shards of the index ``index``: ``index_g<k>`` and ``index_g<k>_p<j>``."""
    pattern = re.compile(rf"{re.escape(index)}_g\d+(_p\d+)?")
    return [n for n in names if pattern.fullmatch(n)]


def renamed(name: str, index: str, new_index: str) -> str:
    """``name`` with the prefix ``index`` replaced; other names are kept."""
    return new_index + name[len(index):] if name.startswith(index) else name


def check_renames(registry: str, renames: dict[str, str]) -> None:
    """Refuse renames that would clash or race a build; ValueError says why."""
    with open(os.path.join(registry, "index.json")) as f:
        entries = json.load(f).get("index") or {}
    for old, new in renames.items():
        if old not in entries:
            raise ValueError(f"Shard '{old}' not found in registry")
        check_index_name(new)
        if new in entries and new not in renames:
            raise ValueError(f"Shard '{new}' is already registered")
        if os.path.lexists(os.path.join(registry, new)) and new not in renames:
            raise ValueError(f"{os.path.join(registry, new)} already exists")
        logs = os.path.join(registry, "logs", new)
        if os.path.lexists(logs) and new not in renames:
            raise ValueError(f"{logs} already exists")
    for session, state in sessions(registry).items():
        if active_jobs(state):
            raise ValueError(f"Jobs of session '{session}' are still queued or running")
        building = {t["shard"] for t in state.tasks.values() if not state.task_done(t)}
        if building & set(renames):
            raise ValueError(
                f"Session '{session}' still builds {', '.join(sorted(building & set(renames)))}: "
                "finish or replan it first"
            )


def rename_shards(registry: str, renames: dict[str, str]) -> str:
    """Rename the shards ``renames`` (old -> new) and their logs, in one
    ``index.json`` write under the registry lock; return the backup of
    ``index.json``. A failure undoes the folder renames already made."""
    registry = os.path.realpath(registry)
    with locked(BuildPaths(registry, "").lock):
        check_renames(registry, renames)
        json_path = os.path.join(registry, "index.json")
        backup = f"{json_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        shutil.copy2(json_path, backup)
        logger.info(f"Backed up {json_path} to {backup}")
        with open(json_path) as f:
            data = json.load(f)

        done: list[tuple[str, str]] = []
        try:
            for old, new in renames.items():
                for folder in (registry, os.path.join(registry, "logs")):
                    src, dst = os.path.join(folder, old), os.path.join(folder, new)
                    if os.path.lexists(src):
                        os.rename(src, dst)
                        done.append((src, dst))
                        logger.info(f"Renamed {src} -> {dst}")
            # same order, new keys
            data["index"] = {renames.get(k, k): v for k, v in data["index"].items()}
            replace_atomically(json_path, json.dumps(data, indent=4))
        except OSError:
            for src, dst in reversed(done):
                try:
                    os.rename(dst, src)
                except OSError as e:
                    logger.error(f"Could not undo {src} -> {dst}: {e}")
            raise
        logger.info(f"Wrote {json_path}")

    for new in renames.values():
        _rename_stats(os.path.join(registry, "logs", new, STATS_FILE), new)
    return backup


def _rename_stats(path: str, shard: str) -> None:
    """The ``shard`` field of the stats of a renamed shard; failing only warns."""
    if not os.path.isfile(path):
        return
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        data["shard"] = shard
        replace_atomically(path, yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    except (OSError, yaml.YAMLError) as e:
        logger.warning(f"Could not update {path}: {e}")


def check_layout_rename(compose_dir: str, index: str, new_index: str) -> None:
    """Refuse a compose folder rename bound to fail, before any shard is renamed."""
    src = os.path.join(compose_dir, index)
    dst = os.path.join(compose_dir, new_index)
    if not os.path.isdir(src):
        raise ValueError(f"No compose folder {src}")
    if os.path.lexists(dst):
        raise ValueError(f"{dst} already exists")


def rename_layout(compose_dir: str, index: str, new_index: str) -> Optional[str]:
    """Rename ``COMPOSE_DIR/index/`` to ``COMPOSE_DIR/new_index/`` and the
    names its layout records; return the new layout path, None without one.

    The sessions already composed keep the old names in their files: they
    are built, the next ``compose -n new_index`` starts from the layout.
    """
    check_layout_rename(compose_dir, index, new_index)
    src = os.path.join(compose_dir, index)
    dst = os.path.join(compose_dir, new_index)
    layout = os.path.join(src, LAYOUT_FILE)
    if not os.path.isfile(layout):
        os.rename(src, dst)
        logger.info(f"Renamed {src} -> {dst} (no layout)")
        return None
    with locked(layout_lock(layout)):
        with open(layout) as f:
            data = yaml.safe_load(f) or {}
        spans = (data.get("data") or {}).get("map") or {}
        for span, entry in spans.items():
            if isinstance(entry, str):  # layouts written before sharding
                spans[span] = renamed(entry, index, new_index)
                continue
            entry["name"] = renamed(entry["name"], index, new_index)
            for sh in entry.get("shards") or []:
                sh["name"] = renamed(sh["name"], index, new_index)
        replace_atomically(layout, yaml.dump(data, default_flow_style=False, sort_keys=True))
    if remove_if_free(layout_lock(layout)) is False:
        raise ValueError(f"{layout} is in use (compose or apply running): not moved")
    os.rename(src, dst)
    logger.info(f"Renamed {src} -> {dst}")
    return os.path.join(dst, LAYOUT_FILE)
