"""Where a build stands: step states, and ``BUILD_DIR/assets/<session>/progress.yaml``.

``apply`` (``runner.PlanRunner``) records each step it runs in a state file,
``assets/<session>/<shard>/state/<step>.json`` (``<run>`` or ``merge``), one per
step, so the tasks of a SLURM array never write the same file. The status of a
step comes from the build directory first, then from its state file, then from
the submissions of ``submit.sh`` (``slurm/submitted.tsv``):

- ``SUCCESS``: its run is complete, or its shard holds the samples of its task;
- ``FAILED`` / ``CANCELLED``: as recorded, with its log;
- ``RUNNING``: recorded; when its job is gone from ``squeue`` (checked on
  request), ``LOST``: the job ended without a status (out of memory, node);
- ``PENDING``: nothing recorded yet, with its job when it was submitted.
"""

import json
import logging
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import yaml

from pykmhelpers.core.kmindex_paths import chunk_problems
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import MERGE

logger = logging.getLogger(__name__)

RUNNING = "RUNNING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
LOST = "LOST"
PENDING = "PENDING"

PROGRESS_FILE = "progress.yaml"
SUBMITTED_FILE = os.path.join("slurm", "submitted.tsv")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def job_id() -> str:
    """The SLURM job running this process (``<array>_<task>`` for an array task)."""
    array, task = os.environ.get("SLURM_ARRAY_JOB_ID"), os.environ.get("SLURM_ARRAY_TASK_ID")
    if array and task:
        return f"{array}_{task}"
    return os.environ.get("SLURM_JOB_ID") or f"pid {os.getpid()}"


def fof_names(path: str) -> set[str]:
    """Sample names of a fof (``name: path;path`` lines)."""
    try:
        with open(path) as f:
            return {n for n in (line.split(":", 1)[0].strip() for line in f) if n}
    except OSError:
        return set()


def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


class BuildState:
    """What the build directory, the state files and the submissions tell of a plan."""

    def __init__(self, plan: dict, paths: BuildPaths) -> None:
        self.plan = plan
        self.paths = paths
        self.tasks: dict[str, dict] = plan.get("tasks") or {}

    # --- the build directory

    def registered(self, shard: str) -> bool:
        try:
            with open(os.path.join(self.paths.registry, "index.json")) as f:
                return shard in (json.load(f).get("index") or {})
        except (OSError, ValueError):
            return False

    def published(self, shard: str) -> set[str]:
        return fof_names(os.path.join(self.paths.shard(shard), "kmtricks.fof"))

    def task_dir(self, task: dict) -> str:
        return self.paths.task(task["dir"].rstrip("/"))

    def task_samples(self, task: dict) -> set[str]:
        names: set[str] = set()
        for run in task["chunks"]:
            names |= fof_names(os.path.join(self.task_dir(task), f"{run}.fof"))
        return names

    def task_done(self, task: dict) -> bool:
        """The shard is registered and holds every sample of the task's chunks."""
        if not self.registered(task["shard"]):
            return False
        return self.task_samples(task) <= self.published(task["shard"])

    def chunk_complete(self, task: dict, run: str) -> bool:
        return not chunk_problems(self.paths.run(run), task["partitions"])

    # --- state files

    def state_path(self, task: dict, step: str) -> str:
        return os.path.join(self.task_dir(task), "state", f"{step}.json")

    def read_state(self, task: dict, step: str) -> dict:
        try:
            with open(self.state_path(task, step)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def write_state(self, task: dict, step: str, status: str, **fields) -> None:
        state = {"status": status, "job": job_id(), "node": socket.gethostname(), **fields}
        if status == RUNNING:
            state["started"] = now()
        else:
            state["started"] = self.read_state(task, step).get("started")
            state["finished"] = now()
        _atomic_write(self.state_path(task, step), json.dumps(state) + "\n")

    # --- submissions

    def submitted(self) -> dict[str, str]:
        """Last SLURM id of each job submitted by ``submit.sh``."""
        ids: dict[str, str] = {}
        try:
            with open(os.path.join(self.paths.assets, SUBMITTED_FILE)) as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 2 and parts[0]:
                        ids[parts[0]] = parts[1]
        except OSError:
            pass
        return ids

    # --- status

    def step_status(
        self, task: dict, step: str, job_of: Optional[str], alive=None
    ) -> tuple[str, str]:
        """``(status, detail)`` of one step; ``alive(job) -> bool | None`` checks
        that a RUNNING job still exists (None: not checked)."""
        if self.task_done(task) or (step != MERGE and self.chunk_complete(task, step)):
            return SUCCESS, ""
        state = self.read_state(task, step)
        status = state.get("status")
        log = self._relative(state.get("log"))
        if status in (FAILED, CANCELLED):
            detail = f"log: {log}" if log else ""
            if state.get("error"):
                detail = f"{detail}, {state['error']}" if detail else state["error"]
            return status, detail
        if status == RUNNING:
            job = state.get("job", "?")
            if alive is not None and job and not job.startswith("pid ") and alive(job) is False:
                return LOST, f"job {job} ended without a status: out of memory or node failure, see its SLURM log"
            since = (state.get("started") or "")[11:16]
            return RUNNING, f"job {job}, {state.get('node', '?')}, since {since}"
        if job_of:
            if alive is not None and alive(job_of) is False:
                # a step before it failed, or its dependency was cancelled
                return PENDING, f"job {job_of} ended without running it: submit again"
            return PENDING, f"job {job_of}"
        return PENDING, ""

    def progress(self, check_jobs: bool = False) -> dict:
        """The progress tree: per shard, the status of each step."""
        alive = squeue_alive if check_jobs and shutil.which("squeue") else None
        submitted = self.submitted()
        shards: dict[str, dict] = {}
        counts = {"done": 0, "failed": 0, "running": 0, "pending": 0}
        for task in self.tasks.values():
            job_of = {
                step: submitted.get(job)
                for job, steps in (task.get("jobs") or {}).items()
                for step in steps
            }
            steps = list(task["chunks"]) + ([MERGE] if task.get("merge") else [])
            entry: dict[str, str] = {}
            statuses = []
            for step in steps:
                status, detail = self.step_status(task, step, job_of.get(step), alive)
                statuses.append(status)
                entry[step] = f"{status} ({detail})" if detail else status
            shards[task["shard"]] = entry
            if all(s == SUCCESS for s in statuses):
                counts["done"] += 1
            elif any(s in (FAILED, CANCELLED, LOST) for s in statuses):
                counts["failed"] += 1
            elif RUNNING in statuses:
                counts["running"] += 1
            else:
                counts["pending"] += 1
        return {
            "updated": now(),
            "summary": {"shards": len(shards), **counts},
            "shards": shards,
        }

    def write_progress(self, check_jobs: bool = False) -> dict:
        """Write ``progress.yaml`` (atomically: concurrent jobs each write a
        complete snapshot); return the tree."""
        tree = self.progress(check_jobs)
        _atomic_write(
            os.path.join(self.paths.assets, PROGRESS_FILE),
            yaml.safe_dump(tree, sort_keys=False, default_flow_style=False, width=1 << 16),
        )
        return tree

    def _relative(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        try:
            return os.path.relpath(path, self.paths.build_dir)
        except ValueError:
            return path


def overall(tree: dict) -> str:
    """Overall status of a progress tree: SUCCESS, FAILED, RUNNING or PENDING."""
    s = tree["summary"]
    if s["done"] == s["shards"]:
        return SUCCESS
    if s["failed"]:
        return FAILED
    return RUNNING if s["running"] else PENDING


def render(tree: dict, shards: Optional[list[str]] = None) -> str:
    """The progress tree as text, for the terminal and the mails."""
    s = tree["summary"]
    lines = [
        f"{overall(tree)}: {s['done']}/{s['shards']} shard(s) done, {s['failed']} failed, "
        f"{s['running']} running, {s['pending']} pending ({tree['updated']})"
    ]
    for shard, steps in tree["shards"].items():
        if shards and shard not in shards:
            continue
        lines.append(f"{shard}:")
        lines += [f"  {step}: {status}" for step, status in steps.items()]
    return "\n".join(lines)


def squeue_alive(job: str) -> Optional[bool]:
    """True while ``job`` is queued or running, None when squeue cannot tell."""
    try:
        r = subprocess.run(
            ["squeue", "-h", "-j", job, "-o", "%T"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        # an unknown (finished, purged) job id is an error for squeue
        return False if "Invalid job id" in r.stderr else None
    return bool(r.stdout.strip())


# ---
# ONE LINE PER SHARD (--show-progress)

BAR_LEN = 12
MAX_RUNNING_SHOWN = 3
_CHUNK = re.compile(r"chunk\d+$")
_COLORS = {SUCCESS: "32", FAILED: "31", LOST: "33", CANCELLED: "33"}
_ICONS = {SUCCESS: "✔", FAILED: "✘", LOST: "✘", CANCELLED: "✘"}


@dataclass
class ShardProgress:
    """Where one shard stands: its steps done, running, failed, and its time."""

    shard: str
    state: str  # SUCCESS, FAILED, LOST, CANCELLED, RUNNING, PENDING
    done: int
    total: int
    running: list[tuple[str, datetime]] = field(default_factory=list)  # oldest first
    failed: Optional[tuple[str, str, str]] = None  # status, step, detail
    waiting: int = 0  # steps pending on a submitted job
    started: Optional[datetime] = None
    finished: Optional[datetime] = None

    @property
    def shown(self) -> bool:
        """Started, or ended: a shard not started yet is not shown."""
        return self.started is not None or self.state != PENDING or self.done > 0

    def key(self) -> tuple:
        """What a printed (not redrawn) line follows: steps done, failure, end."""
        ended = self.state if self.state in (SUCCESS, FAILED, LOST, CANCELLED) else None
        return (self.done, self.failed, ended)


def _when(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def shard_progress(state: "BuildState", task: dict, alive=None, submitted=None) -> ShardProgress:
    """Summarize the steps of ``task`` (see ``BuildState.step_status``)."""
    submitted = state.submitted() if submitted is None else submitted
    job_of = {
        step: submitted.get(job)
        for job, steps in (task.get("jobs") or {}).items()
        for step in steps
    }
    steps = list(task["chunks"]) + ([MERGE] if task.get("merge") else [])
    p = ShardProgress(task["shard"], PENDING, 0, len(steps))
    starts, ends = [], []
    for step in steps:
        status, detail = state.step_status(task, step, job_of.get(step), alive)
        recorded = state.read_state(task, step)
        if _when(recorded.get("started")):
            starts.append(_when(recorded["started"]))
        if _when(recorded.get("finished")):
            ends.append(_when(recorded["finished"]))
        if status == SUCCESS:
            p.done += 1
        elif status == RUNNING:
            p.running.append((step, _when(recorded.get("started")) or datetime.now()))
        elif status in (FAILED, LOST, CANCELLED):
            p.failed = p.failed or (status, step, detail)
        elif job_of.get(step) and "ended without" not in detail:
            p.waiting += 1
    p.running.sort(key=lambda r: r[1])
    p.started = min(starts) if starts else None
    if p.done == p.total:
        p.state = SUCCESS
    elif p.failed:
        p.state = p.failed[0]
    elif p.running:
        p.state = RUNNING
    if p.state != RUNNING and ends and not p.running:
        p.finished = max(ends)
    return p


def short_step(step: str) -> str:
    """``chunk5``, ``merge``, or ``run`` for a part built in one run."""
    if step == MERGE:
        return MERGE
    m = _CHUNK.search(step)
    return m.group(0) if m else "run"


def duration(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s}s" if m else f"{s}s"


def shard_line(
    p: ShardProgress, width: int, now: datetime, spinner: str = "⣾", color: bool = False
) -> str:
    """``⣾ idx_g0  [■■■■■■      ] 6/11 (8m3s)  chunk5 (3m12s)``; ``width`` pads the name."""
    filled = round(BAR_LEN * p.done / p.total) if p.total else BAR_LEN
    bar = "■" * filled + " " * (BAR_LEN - filled)
    count = f"{p.done}/{p.total}"
    elapsed = ""
    if p.started:
        elapsed = f"({duration(((p.finished or now) - p.started).total_seconds())})"
    if p.failed:
        status, step, detail = p.failed
        tail = f"{status} {short_step(step)}" + (f" ({detail})" if detail else "")
        if p.running:
            tail += f", {len(p.running)} still running"
    elif p.state == SUCCESS:
        tail = SUCCESS
    elif p.running:
        shown = [f"{short_step(s)} ({duration((now - t).total_seconds())})" for s, t in p.running]
        if len(shown) == 1:
            tail = shown[0]
        else:
            tail = f"{len(shown)} running: " + ", ".join(shown[:MAX_RUNNING_SHOWN])
            tail += ", ..." if len(shown) > MAX_RUNNING_SHOWN else ""
    else:
        tail = "waiting" if spinner else ""
    icon = _ICONS.get(p.state, spinner or "-")
    if color and p.state in _COLORS:
        code = _COLORS[p.state]
        icon, tail = f"\033[{code}m{icon}\033[0m", f"\033[{code}m{tail}\033[0m"
    return f"{icon} {p.shard:<{width}}  [{bar}] {count:<{5}} {elapsed:<9} {tail}".rstrip()
