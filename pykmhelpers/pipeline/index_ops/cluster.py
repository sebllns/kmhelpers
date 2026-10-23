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

# Cluster types, each with the writer of its submission files (WRITERS, below)
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
    check_type(data.get("type"), path)
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


def check_type(cluster_type, path: str = "cluster file") -> str:
    """Refuse a cluster type that has no writer; return it."""
    if not cluster_type:
        raise ValueError(f"{path}: 'type' is required (supported: {', '.join(SCHEDULERS)})")
    if cluster_type not in SCHEDULERS:
        raise ValueError(
            f"{path}: cluster type '{cluster_type}' is not supported "
            f"(supported: {', '.join(SCHEDULERS)})"
        )
    return cluster_type


def write_submission(
    plan: dict,
    cluster: dict,
    assets_dir: str,
    notify: Optional[str] = None,
    notify_level: str = "global",
) -> list[str]:
    """Write the submission files of ``plan`` for its cluster type, to
    ``assets_dir/<type>/``; return their paths."""
    cluster_type = check_type(cluster.get("type"), cluster.get("source", "cluster file"))
    return WRITERS[cluster_type](
        plan, cluster, os.path.join(assets_dir, cluster_type), notify, notify_level
    )


def write_slurm(
    plan: dict,
    cluster: dict,
    slurm_dir: str,
    notify: Optional[str] = None,
    notify_level: str = "global",
) -> list[str]:
    """Write the SLURM files of ``plan`` to ``slurm_dir``; return their paths.

    ``jobs.txt`` (build jobs), ``build.sbatch`` (an array task runs one of
    them), ``merge.sbatch``, ``finish.sbatch`` (after every job: checks the
    registry when everything is done, writes ``progress.yaml``, mails it with
    ``notify``) and ``submit.sh``, which submits what ``apply --pending``
    lists, skipping the jobs still queued: safe to run again.

    With ``notify_level`` ``shard``, the build and merge jobs mail the end of
    their shard (a failed chunk, or the published shard).
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
    shard_mail = (
        f" --notify {shlex.quote(notify)} --notify-level shard --no-notify-final"
        if notify and notify_level == "shard"
        else ""
    )
    # a failed dependency cancels the job, so finish always runs
    no_wait = ["#SBATCH --kill-on-invalid-dep=yes"]

    build_jobs, merges = [], {}
    for task in plan["tasks"].values():
        for job, steps in task["jobs"].items():
            if steps == [MERGE]:
                merges[task["shard"]] = job
            else:
                build_jobs.append(job)
    name = os.path.basename(build_dir.rstrip("/"))
    finish_cmds = [
        "# Every job has ended: check the registry when nothing is pending,",
        "# write progress.yaml (and mail it), fail when the build is not done",
        f"PENDING=$({apply} --pending)",
        "CHECK=0",
        'if [ -z "$PENDING" ]; then',
        f"    kmhelpers manage -r {shlex.quote(build_dir)} check || CHECK=$?",
        "fi",
        f"{apply} --status" + (f" --notify {shlex.quote(notify)}" if notify else ""),
        '[ -z "$PENDING" ] && [ "$CHECK" -eq 0 ]',
    ]

    files = {
        "jobs.txt": "\n".join(build_jobs) + ("\n" if build_jobs else ""),
        "build.sbatch": "\n".join(
            head
            + _sbatch_lines(cluster["jobs"]["build"], f"{name}_build", output)
            + body_head
            + [
                "# Array task i runs line OFFSET + i + 1 of the job list $1",
                'JOB=$(sed -n "$((${2:-0} + SLURM_ARRAY_TASK_ID + 1))p" "$1")',
                f'{apply} --task "$JOB"{shard_mail}',
            ]
        ),
        "merge.sbatch": "\n".join(
            head
            + _sbatch_lines(cluster["jobs"]["merge"], None, single)
            + no_wait
            + body_head
            + ["# $1: a merge job of the plan (<shard>_merge)", f'{apply} --task "$1"{shard_mail}']
        ),
        "finish.sbatch": "\n".join(
            head
            + _sbatch_lines(cluster["jobs"]["check"], f"{name}_finish", single)
            + no_wait
            + body_head
            + finish_cmds
        ),
        "submit.sh": _submit_script(apply, setup, build_dir, merges, cluster),
    }
    # an older plan's check.sbatch is replaced by finish.sbatch
    old = os.path.join(slurm_dir, "check.sbatch")
    if os.path.exists(old):
        os.remove(old)
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
# tasks, then a finish job after everything (progress.yaml, check, mail).
# Safe to run again: only the jobs `apply --pending` lists are submitted (it
# refuses a stale plan), and a job still queued or running is not submitted
# twice. Every submission is appended to submitted.tsv (job, SLURM id).
set -euo pipefail
{setup}
DIR=$(cd "$(dirname "$0")" && pwd)
SUBMITTED="$DIR/submitted.tsv"
mkdir -p {logs}
touch "$SUBMITTED"

# Last SLURM id of a job of the plan, if it is still queued or running
active() {{
    local id
    id=$(awk -F'\t' -v j="$1" '$1 == j {{ id = $2 }} END {{ print id }}' "$SUBMITTED")
    [ -n "$id" ] && squeue -h -j "$id" -o %T 2>/dev/null | grep -q . && echo "$id"
    return 0
}}

{apply} --pending > "$DIR/pending.txt"
: > "$DIR/pending_build.txt"
declare -A ID_OF  # job of the plan -> SLURM id it waits on
while read -r JOB; do
    [ -n "$JOB" ] || continue
    ACTIVE=$(active "$JOB")
    if [ -n "$ACTIVE" ]; then
        ID_OF[$JOB]=$ACTIVE
        echo "$JOB: still queued or running (job $ACTIVE), not submitted again"
    elif ! grep -qxF "$JOB" <(printf '%s\n' {' '.join(shlex.quote(m) for m in merges.values()) or "''"}); then
        echo "$JOB" >> "$DIR/pending_build.txt"
    fi
done < "$DIR/pending.txt"

# 1. Build arrays, split at the cluster MaxArraySize
MAX=$(scontrol show config 2>/dev/null | awk '/^MaxArraySize/ {{print $3}}')
MAX=${{MAX:-1001}}
N=$(wc -l < "$DIR/pending_build.txt")
ALL=()
NEW=0  # jobs submitted by this run
for ((OFFSET = 0; OFFSET < N; OFFSET += MAX)); do
    COUNT=$(( N - OFFSET < MAX ? N - OFFSET : MAX ))
    ARRAY=$(sbatch --parsable --array=0-$((COUNT - 1)){pct} "$DIR/build.sbatch" \
        "$DIR/pending_build.txt" "$OFFSET")
    ARRAY=${{ARRAY%%;*}}
    ALL+=("$ARRAY")
    NEW=$((NEW + COUNT))
    for ((i = 0; i < COUNT; i++)); do
        JOB=$(sed -n "$((OFFSET + i + 1))p" "$DIR/pending_build.txt")
        ID_OF[$JOB]="${{ARRAY}}_$i"
        printf '%s\t%s\n' "$JOB" "${{ARRAY}}_$i" >> "$SUBMITTED"
    done
    echo "build array $ARRAY: $COUNT task(s)"
done

# 2. One merge job per shard, after the build jobs of that shard only
for SHARD in {shards}; do
    MERGE="${{SHARD}}_merge"
    grep -qxF "$MERGE" "$DIR/pending.txt" || continue
    if [ -n "${{ID_OF[$MERGE]:-}}" ]; then ALL+=("${{ID_OF[$MERGE]}}"); continue; fi
    DEP=""
    for JOB in "${{!ID_OF[@]}}"; do
        [[ "$JOB" =~ ^${{SHARD}}_j[0-9]+$ ]] && DEP+=":${{ID_OF[$JOB]}}"
    done
    ID=$(sbatch --parsable -J "$MERGE" ${{DEP:+--dependency=afterok$DEP}} \
        "$DIR/merge.sbatch" "$MERGE")
    ID=${{ID%%;*}}
    ALL+=("$ID")
    NEW=$((NEW + 1))
    printf '%s\t%s\n' "$MERGE" "$ID" >> "$SUBMITTED"
    echo "merge $SHARD: job $ID ${{DEP:+after${{DEP//:/ }}}}"
done
for JOB in "${{!ID_OF[@]}}"; do ALL+=("${{ID_OF[$JOB]}}"); done

# 3. Finish once every job has ended, successful or not: a single finish job
PREVIOUS=$(active finish)
if [ -n "$PREVIOUS" ] && [ "$NEW" -eq 0 ]; then
    echo "finish: job $PREVIOUS still pending, kept (nothing new submitted)"
    ALL=()
elif [ -n "$PREVIOUS" ]; then
    # it would run before the jobs submitted now
    scancel "$PREVIOUS"
    echo "finish: job $PREVIOUS cancelled, replaced"
fi
if [ ${{#ALL[@]}} -gt 0 ]; then
    DEPS=$(printf '%s\n' "${{ALL[@]}}" | sort -u | paste -sd: -)
    ID=$(sbatch --parsable --dependency="afterany:$DEPS" "$DIR/finish.sbatch")
    ID=${{ID%%;*}}
    printf '%s\t%s\n' finish "$ID" >> "$SUBMITTED"
    echo "finish: job $ID"
elif [ -z "$PREVIOUS" ]; then
    echo "nothing pending"
fi
"""


WRITERS = {"slurm": write_slurm}
assert set(WRITERS) == set(SCHEDULERS)
