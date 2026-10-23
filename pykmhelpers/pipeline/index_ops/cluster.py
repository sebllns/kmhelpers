"""The ``--cluster`` file of ``plan``, and the SLURM files written from it.

The file describes the scheduler and the resources of each kind of job::

    type: slurm
    partition: compute
    time: 2-00:00:00
    exclude: [node01]
    max_parallel: 8                   # build array tasks running at once
    output: logs/slurm/%x_%A_%a.out   # relative to BUILD_DIR
    setup: |                          # run before kmhelpers in every job
      export PATH=...
    extra: []                         # other sbatch options, as is
    jobs:
      build: {cpus: 24, mem: 120G}
      merge: {cpus: 24, mem: 120G}
      check: {cpus: 1, mem: 4G, time: "1:00:00"}
    limits: {files: 131072, maps: 65530}   # compute-node limits, optional

The plan is sized from it: chunks from ``jobs.build`` (threads = cpus, ram =
mem), merges from ``jobs.merge``, plus ``limits`` (else detected on the node
``plan`` runs on). ``write_slurm`` writes ``assets/<session>/slurm/``.
"""

import json
import os
import re
import shlex
from typing import Optional

import yaml

from pykmhelpers.pipeline.index_ops.plan_file import MERGE

SCHEDULERS = ("slurm",)
JOB_KINDS = ("build", "merge", "check")
# Keys a job kind may set, also accepted at the top level as defaults
JOB_KEYS = {"partition", "time", "exclude", "account", "qos", "constraint", "cpus", "mem", "extra"}
TOP_KEYS = JOB_KEYS | {"type", "max_parallel", "output", "setup", "jobs", "limits"}
LIMIT_KEYS = {"files", "maps"}
DEFAULTS = {"output": "logs/slurm/%x_%A_%a.out", "max_parallel": 0, "setup": ""}
# The check job only reads the registry
CHECK_DEFAULTS = {"cpus": 1, "mem": "4G"}

_MEM = re.compile(r"^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$", re.I)
_UNITS = {"": 1 << 20, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}


def mem_bytes(value) -> int:
    """``120G``, ``4096M`` or a number of MB (as sbatch) -> bytes."""
    m = _MEM.match(str(value).strip())
    if not m:
        raise ValueError(f"Invalid memory '{value}' (expected e.g. 120G, 4096M)")
    return int(float(m.group(1)) * _UNITS[m.group(2).upper()])


def load_cluster(path: str) -> dict:
    """Load and validate a cluster file; resolve each job kind."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    unknown = set(data) - TOP_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown key(s) {', '.join(sorted(unknown))}")
    if data.get("type") not in SCHEDULERS:
        raise ValueError(f"{path}: 'type' must be one of {', '.join(SCHEDULERS)}")
    jobs = data.get("jobs") or {}
    unknown = set(jobs) - set(JOB_KINDS)
    if unknown:
        raise ValueError(f"{path}: unknown job kind(s) {', '.join(sorted(unknown))}")
    limits = data.get("limits") or {}
    unknown = set(limits) - LIMIT_KEYS
    if unknown:
        raise ValueError(
            f"{path}: unknown limit(s) {', '.join(sorted(unknown))} "
            f"(cpus and mem are set per job kind, under jobs)"
        )

    resolved: dict = {k: data.get(k, DEFAULTS.get(k)) for k in ("type", "max_parallel", "output", "setup")}
    resolved["source"] = os.path.realpath(path)
    resolved["limits"] = dict(limits)
    resolved["jobs"] = {}
    base = {k: v for k, v in data.items() if k in JOB_KEYS}
    for kind in JOB_KINDS:
        entry = jobs.get(kind) or {}
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: jobs.{kind} must be a mapping")
        unknown = set(entry) - JOB_KEYS
        if unknown:
            raise ValueError(f"{path}: unknown key(s) in jobs.{kind}: {', '.join(sorted(unknown))}")
        if kind == "check":
            job = {**base, **CHECK_DEFAULTS, **entry}
        else:
            job = {**base, **entry}
            if not (job.get("cpus") and job.get("mem")):
                raise ValueError(f"{path}: jobs.{kind} needs cpus and mem")
        job["mem_bytes"] = mem_bytes(job["mem"])
        job["extra"] = list(job.get("extra") or [])
        if isinstance(job.get("exclude"), str):
            job["exclude"] = [job["exclude"]]
        resolved["jobs"][kind] = job
    return resolved


def limits_for(cluster: dict, kind: str, safety_margin: float = 1.0) -> str:
    """``--limits`` JSON line of the jobs of ``kind``: ``safety_margin`` of
    their memory, so a job does not size itself to its whole allocation."""
    job = cluster["jobs"][kind]
    limits = {"ram": int(job["mem_bytes"] * safety_margin), "threads": int(job["cpus"])}
    limits.update(cluster.get("limits") or {})
    return json.dumps(limits)


def _sbatch_lines(job: dict, name: Optional[str], output: str) -> list[str]:
    lines = []
    if name:
        lines.append(f"#SBATCH -J {name}")
    for key, flag in (("partition", "-p"), ("time", "-t"), ("account", "-A"), ("qos", "--qos")):
        if job.get(key):
            lines.append(f"#SBATCH {flag} {job[key]}")
    if job.get("constraint"):
        lines.append(f"#SBATCH --constraint={job['constraint']}")
    if job.get("exclude"):
        lines.append(f"#SBATCH --exclude={','.join(job['exclude'])}")
    lines += [f"#SBATCH -c {job['cpus']}", f"#SBATCH --mem={job['mem']}", f"#SBATCH -o {output}"]
    lines += [f"#SBATCH {opt}" for opt in job["extra"]]
    return lines


def write_slurm(plan: dict, cluster: dict, slurm_dir: str) -> list[str]:
    """Write the SLURM files of ``plan`` to ``slurm_dir``; return their paths.

    ``jobs.txt`` (build jobs), ``build.sbatch`` (an array task runs one of
    them), ``merge.sbatch``, ``check.sbatch`` and ``submit.sh``, which
    submits what ``apply --pending`` lists: safe to run again.
    """
    os.makedirs(slurm_dir, exist_ok=True)
    build_dir = plan["build_dir"]
    definition = plan["definition"]
    apply = f"kmhelpers apply {shlex.quote(definition)} -o {shlex.quote(build_dir)}"
    output = os.path.join(build_dir, cluster["output"])
    single = os.path.join(os.path.dirname(output), "%x_%j.out")
    setup = (cluster.get("setup") or "").rstrip("\n")
    head = ["#!/usr/bin/env bash"]
    body_head = ["set -euo pipefail"] + ([setup] if setup else [])

    build_jobs, merges = [], {}
    for task in plan["tasks"].values():
        for job, steps in task["jobs"].items():
            if steps == [MERGE]:
                merges[task["shard"]] = job
            else:
                build_jobs.append(job)
    name = os.path.basename(build_dir.rstrip("/"))

    files = {
        "jobs.txt": "\n".join(build_jobs) + ("\n" if build_jobs else ""),
        "build.sbatch": "\n".join(
            head
            + _sbatch_lines(cluster["jobs"]["build"], f"{name}_build", output)
            + body_head
            + [
                "# Array task i runs line OFFSET + i + 1 of the job list $1",
                'JOB=$(sed -n "$((${2:-0} + SLURM_ARRAY_TASK_ID + 1))p" "$1")',
                f'{apply} --job "$JOB"',
            ]
        ),
        "merge.sbatch": "\n".join(
            head
            + _sbatch_lines(cluster["jobs"]["merge"], None, single)
            + body_head
            + ["# $1: a merge job of the plan (<shard>_merge)", f'{apply} --job "$1"']
        ),
        "check.sbatch": "\n".join(
            head
            + _sbatch_lines(cluster["jobs"]["check"], f"{name}_check", single)
            + body_head
            + [f"kmhelpers manage -r {shlex.quote(build_dir)} check"]
        ),
        "submit.sh": _submit_script(apply, setup, build_dir, merges, cluster),
    }
    written = []
    for file_name, text in files.items():
        path = os.path.join(slurm_dir, file_name)
        with open(path, "w") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        if file_name.endswith((".sh", ".sbatch")):
            os.chmod(path, 0o755)
        written.append(path)
    return written


def _submit_script(apply: str, setup: str, build_dir: str, merges: dict, cluster: dict) -> str:
    throttle = int(cluster.get("max_parallel") or 0)
    pct = f"%{throttle}" if throttle else ""
    shards = " ".join(shlex.quote(s) for s in merges)
    logs = shlex.quote(os.path.dirname(os.path.join(build_dir, cluster["output"])))
    return f"""#!/usr/bin/env bash
# Submit the plan: build array, one merge job per shard after its own array
# tasks, then a check job after everything. Safe to run again: only the jobs
# `apply --pending` lists are submitted (and it refuses a stale plan).
set -euo pipefail
{setup}
DIR=$(cd "$(dirname "$0")" && pwd)
mkdir -p {logs}

{apply} --pending > "$DIR/pending.txt"
grep -vxF -f <(printf '%s\\n' {' '.join(shlex.quote(m) for m in merges.values()) or "''"}) \\
    "$DIR/pending.txt" > "$DIR/pending_build.txt" || true

# 1. Build arrays, split at the cluster MaxArraySize
MAX=$(scontrol show config 2>/dev/null | awk '/^MaxArraySize/ {{print $3}}')
MAX=${{MAX:-1001}}
N=$(wc -l < "$DIR/pending_build.txt")
declare -A TASK_OF  # line number (from 1) -> <array job>_<task>
ALL=()
for ((OFFSET = 0; OFFSET < N; OFFSET += MAX)); do
    COUNT=$(( N - OFFSET < MAX ? N - OFFSET : MAX ))
    ARRAY=$(sbatch --parsable --array=0-$((COUNT - 1)){pct} "$DIR/build.sbatch" \\
        "$DIR/pending_build.txt" "$OFFSET")
    ARRAY=${{ARRAY%%;*}}
    ALL+=("$ARRAY")
    for ((i = 0; i < COUNT; i++)); do TASK_OF[$((OFFSET + i + 1))]="${{ARRAY}}_$i"; done
    echo "build array $ARRAY: $COUNT task(s)"
done

# 2. One merge job per shard, after the array tasks of that shard only
for SHARD in {shards}; do
    grep -qxF "${{SHARD}}_merge" "$DIR/pending.txt" || continue
    DEP=""
    while IFS=: read -r LINE _; do
        DEP+=":${{TASK_OF[$LINE]}}"
    done < <(grep -n "^${{SHARD}}_j[0-9]*$" "$DIR/pending_build.txt" || true)
    ID=$(sbatch --parsable -J "${{SHARD}}_merge" ${{DEP:+--dependency=afterok$DEP}} \\
        "$DIR/merge.sbatch" "${{SHARD}}_merge")
    ALL+=("${{ID%%;*}}")
    echo "merge $SHARD: job ${{ID%%;*}} ${{DEP:+after${{DEP//:/ }}}}"
done

# 3. Check the registry once everything succeeded
if [ ${{#ALL[@]}} -gt 0 ]; then
    ID=$(sbatch --parsable --dependency="afterok:$(IFS=:; echo "${{ALL[*]}}")" "$DIR/check.sbatch")
    echo "check: job ${{ID%%;*}}"
else
    echo "nothing pending"
fi
"""
