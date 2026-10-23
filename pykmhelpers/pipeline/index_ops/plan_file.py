"""The plan manifest, ``BUILD_DIR/assets/<session>/plan.yaml``.

``plan`` writes it next to the scripts of every task; ``apply`` loads it and
runs the scripts it lists. A **task** is one session's samples added to one
index (``<shard>_<session>``, or an index definition), keyed by its part
name::

    tasks:
      <part>:
        shard: <index in BUILD_DIR>
        dir: <shard>/                 scripts and fofs, under assets/<session>/
        samples, partitions, minim_size, threads, ...
        chunks: {<run>: {samples: n}} kmtricks runs, <dir>/<run>.sh
        merge: {script: merge.sh, expects, mode, steps, ...}
        jobs: {<job>: [<run>..., merge]}

A **job** is what ``apply --task <job>`` and a SLURM array task run: some chunks of
one task, or its merge (``MERGE``).
"""

import hashlib
import logging
import math
import os
from datetime import datetime
from typing import Optional

import yaml

import pykmhelpers

logger = logging.getLogger(__name__)

PLAN_TYPE = "plan"
MERGE = "merge"


def job_names(shard: str, chunks: list[str], has_merge: bool, per_job: int) -> dict:
    """Jobs of one task: ``{job: [runs..., MERGE]}``.

    ``per_job`` 0 (or at least the chunk count): one job ``<shard>``, its
    chunks then its merge. Else ``<shard>_j<k>`` jobs of up to ``per_job``
    chunks, then ``<shard>_merge``, run after all of them.
    """
    if per_job <= 0 or len(chunks) <= per_job:
        return {shard: list(chunks) + ([MERGE] if has_merge else [])}
    jobs: dict[str, list[str]] = {}
    for k in range(math.ceil(len(chunks) / per_job)):
        jobs[f"{shard}_j{k}"] = list(chunks[k * per_job : (k + 1) * per_job])
    if has_merge:
        jobs[f"{shard}_merge"] = [MERGE]
    return jobs


def file_hashes(paths: list[str]) -> dict[str, str]:
    """``{path: sha256}`` of the input files a plan was made from."""
    hashes = {}
    for path in sorted(set(os.path.realpath(p) for p in paths if p)):
        if os.path.isfile(path):
            hashes[path] = _sha256(path)
    return hashes


def stale_files(hashes: dict[str, str]) -> list[str]:
    """Input files of a plan that changed (or vanished) since it was made."""
    return [
        path
        for path, digest in hashes.items()
        if not os.path.isfile(path) or _sha256(path) != digest
    ]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def new_plan(
    definition: str,
    build_dir: str,
    session: str,
    inputs: list[str],
    options: dict,
    tasks: dict,
) -> dict:
    return {
        "type": PLAN_TYPE,
        "kmhelpers": pykmhelpers.__version__,
        "created": datetime.now().isoformat(timespec="seconds"),
        "definition": definition,
        "build_dir": build_dir,
        "session": session,
        "fingerprint": {"files": file_hashes(inputs)},
        "options": options,
        "tasks": tasks,
    }


def write_plan(path: str, plan: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(plan, f, sort_keys=False, default_flow_style=False, width=1 << 16)
    logger.info(f"Plan written to {path}")


def load_plan(path: str) -> dict:
    """Load ``plan.yaml``; refuse a missing or foreign file."""
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"No plan at {path}: run `kmhelpers plan` with the same INPUT and -o first"
        )
    with open(path) as f:
        plan = yaml.safe_load(f) or {}
    if plan.get("type") != PLAN_TYPE:
        raise ValueError(f"Not a kmhelpers plan: {path}")
    return plan


def check_fresh(plan: dict, definition: Optional[str] = None) -> None:
    """Refuse a plan made from other inputs, or by another kmhelpers version."""
    problems = []
    if definition and os.path.realpath(definition) != plan.get("definition"):
        problems.append(f"it was made for {plan.get('definition')}, not {definition}")
    if plan.get("kmhelpers") != pykmhelpers.__version__:
        problems.append(
            f"it was made by kmhelpers {plan.get('kmhelpers')}, "
            f"this is {pykmhelpers.__version__}"
        )
    changed = stale_files(plan.get("fingerprint", {}).get("files", {}))
    if changed:
        shown = ", ".join(changed[:3]) + (f" (+{len(changed) - 3})" if len(changed) > 3 else "")
        problems.append(f"its inputs changed: {shown}")
    if problems:
        raise ValueError(
            "The plan is stale: " + "; ".join(problems) + ". Run `kmhelpers plan` again."
        )
