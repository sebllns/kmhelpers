"""Repairs of a registry (``kmhelpers manage check --autorepair``).

kmindex finds a shard at ``<registry>/<name>`` and follows it when it is a
symlink (``read_symlink``: a relative target is resolved against the current
directory, not the registry). Moving the registry or its shards leaves the
root ``path`` of ``index.json`` stale and the links dangling. The repairs:

- ``root``: set ``path`` to the registry;
- ``absolute``: make a relative link that resolves absolute;
- ``relink``: link a lost shard to a folder found elsewhere, holding the same
  samples in the same order (never another version of it);
- ``remove``: drop a shard found nowhere from ``index.json``.
"""

import glob
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pykmhelpers.core.file_lock import locked
from pykmhelpers.core.kmindex_layout import check_index_structure, load_fof_file
from pykmhelpers.pipeline.index_ops.paths import RESERVED_NAMES, BuildPaths

logger = logging.getLogger(__name__)

ROOT, ABSOLUTE, RELINK, REMOVE = "root", "absolute", "relink", "remove"


@dataclass
class Repair:
    kind: str
    shard: Optional[str]
    old: Optional[str]
    new: Optional[str]

    def __str__(self) -> str:
        if self.kind == ROOT:
            return f"path: {self.old} -> {self.new}"
        if self.kind == ABSOLUTE:
            return f"{self.shard}: relative link {self.old} -> {self.new}"
        if self.kind == RELINK:
            return f"{self.shard}: relinked -> {self.new}"
        return f"{self.shard}: not found, removed from index.json"


def _json_path(registry: str) -> str:
    return os.path.join(registry, "index.json")


def _load(registry: str) -> dict:
    with open(_json_path(registry)) as f:
        return json.load(f)


def matches(path: str, entry: dict) -> bool:
    """``path`` is a complete index holding the samples of ``entry``, in order."""
    try:
        # samples first: a cheap test, and no structure warnings for other folders
        if load_fof_file(os.path.join(path, "kmtricks.fof")) != list(entry.get("samples") or []):
            logger.debug(f"Candidate {path}: other samples")
            return False
        if not check_index_structure(path, int(entry.get("nb_partitions") or 0)):
            logger.debug(f"Candidate {path}: incomplete structure")
            return False
        return True
    except (OSError, ValueError) as e:
        logger.debug(f"Candidate {path}: {e}")
        return False


def candidates(name: str, registry: str, old_root: str, old_target: Optional[str], search_dirs) -> list[str]:
    """Where a lost shard may be, most likely first."""
    found = []
    target_name = os.path.basename(old_target.rstrip(os.sep)) if old_target else None
    roots = [old_root] if old_root and os.path.realpath(old_root) != registry else []
    for root in roots:
        found.append(os.path.join(root, name))
        if target_name:
            found.append(os.path.join(root, target_name))
    found += sorted(glob.glob(os.path.join(glob.escape(registry), "work", "*", "previous", name)))
    for d in search_dirs:
        found.append(os.path.join(d, name))
        found += sorted(glob.glob(os.path.join(glob.escape(d), "*", name)))
        if target_name:
            found.append(os.path.join(d, target_name))
    unique = []
    for path in found:
        real = os.path.realpath(path)
        if real not in unique and os.path.isdir(real):
            unique.append(real)
    logger.debug(f"Candidates for {name}: {unique or 'none'}")
    return unique


def find_shard(entry: dict, places: list[str]) -> Optional[str]:
    return next((p for p in places if matches(p, entry)), None)


def plan_repairs(registry: str, shards: Optional[list[str]] = None, search_dirs=()) -> tuple[list[Repair], list[str]]:
    """Repairs of the registry, limited to ``shards`` (the root path is always
    checked), and the index folders of the registry that are not registered."""
    registry = os.path.realpath(registry)
    data = _load(registry)
    entries = data.get("index") or {}
    old_root = data.get("path") or ""
    repairs = []
    logger.info(f"Planning the repairs of {registry} ({len(entries)} shard(s))")
    if old_root != registry:
        logger.debug(f"Root path {old_root!r} is not the registry")
        repairs.append(Repair(ROOT, None, old_root, registry))

    for name in shards if shards is not None else list(entries):
        link = os.path.join(registry, name)
        target = os.readlink(link) if os.path.islink(link) else None
        if os.path.exists(link):
            if target and not os.path.isabs(target):
                logger.debug(f"{name}: relative link {target}")
                repairs.append(Repair(ABSOLUTE, name, target, os.path.realpath(link)))
            continue
        logger.info(f"{name}: " + (f"dangling link {target}" if target else "folder missing") + ", searching")
        places = candidates(name, registry, old_root, target, search_dirs)
        found = find_shard(entries[name], places)
        repairs.append(Repair(RELINK, name, target, found) if found else Repair(REMOVE, name, target, None))
        logger.info(f"{name}: found in {found}" if found else f"{name}: not found in {len(places)} candidate(s)")

    unregistered = []
    for entry in sorted(os.listdir(registry)):
        path = os.path.join(registry, entry)
        if entry in entries or entry in RESERVED_NAMES or entry.startswith("."):
            continue
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "kmtricks.fof")):
            unregistered.append(entry)
    logger.info(f"{len(repairs)} repair(s) planned, {len(unregistered)} unregistered folder(s)")
    return repairs, unregistered


def _replace_link(link: str, target: str) -> None:
    if os.path.islink(link):
        os.unlink(link)
    os.symlink(target, link, target_is_directory=True)


def apply_repairs(registry: str, repairs: list[Repair]) -> tuple[Optional[str], list[str]]:
    """Apply ``repairs`` under the registry lock, after a timestamped backup of
    ``index.json``; return the backup and the errors. A failed repair does
    not stop the others."""
    registry = os.path.realpath(registry)
    if not repairs:
        return None, []
    errors = []
    with locked(BuildPaths(registry, "").lock):
        json_path = _json_path(registry)
        backup = f"{json_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        shutil.copy2(json_path, backup)
        logger.info(f"Backed up {json_path} to {backup}")
        data = _load(registry)
        for r in repairs:
            try:
                if r.kind == ROOT:
                    data["path"] = r.new
                    continue
                assert r.shard
                link = os.path.join(registry, r.shard)
                if r.kind in (ABSOLUTE, RELINK):
                    assert r.new
                    _replace_link(link, r.new)
                elif r.kind == REMOVE:
                    if os.path.islink(link):
                        os.unlink(link)
                    data["index"].pop(r.shard, None)
                logger.info(f"Repaired {r}")
            except OSError as e:
                logger.warning(f"Repair failed, {r}: {e}")
                errors.append(f"{r}: {e}")
        tmp = f"{json_path}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp, json_path)
        logger.info(f"Wrote {json_path}")
    return backup, errors
