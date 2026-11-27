"""Resources of a command: wall and CPU time, peak RAM, peak open files, peak storage.

``run_monitored`` runs a command and writes its resources to a JSON file. The chunk
scripts wrap ``kmtricks pipeline`` with it and the publish scripts every ``kmindex
merge`` step (``kmhelpers manage monitor``); ``stats.write_run_stats`` and
``stats.write_shard_stats`` fold the files into the run and shard stats.

* wall, CPU user and system time, and ``peak_rss_max_proc_kb`` (the largest RSS of one
  process) come from ``wait4``. The kernel reports 0 for some statically linked
  binaries (seen with kmindex 0.7.1 on Linux aarch64): ``peak_rss_tree_kb`` is the
  sampled value to use then.
* ``peak_rss_tree_kb``, ``peak_open_files`` (``/proc/<pid>/fd``, once per process of
  the tree) and ``peak_disk_bytes`` / ``peak_disk_inodes`` (a walk of the watched
  directories) are sampled: lower bounds. Without ``/proc`` (macOS) only the ``wait4``
  values are recorded.
"""

import json
import os
import resource
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Optional, Sequence

PROC = "/proc"


def _tree(root: int) -> list[int]:
    kids: dict[int, list[int]] = {}
    for d in os.listdir(PROC):
        if not d.isdigit():
            continue
        try:
            with open(os.path.join(PROC, d, "stat")) as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        kids.setdefault(ppid, []).append(int(d))
    out, todo = [], [root]
    while todo:
        p = todo.pop()
        out.append(p)
        todo.extend(kids.get(p, []))
    return out


def _rss_kb(pid: int) -> int:
    try:
        with open(os.path.join(PROC, str(pid), "status")) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _nfds(pid: int) -> int:
    try:
        return len(os.listdir(os.path.join(PROC, str(pid), "fd")))
    except OSError:
        return 0


def disk_usage(dirs: Sequence[str]) -> tuple[int, int]:
    """Allocated bytes and entry count of ``dirs`` (missing dirs count 0)."""
    total, entries = 0, 0
    for d in dirs:
        for root, dnames, fnames in os.walk(d, onerror=lambda e: None):
            entries += len(dnames) + len(fnames)
            for n in fnames:
                try:
                    total += os.lstat(os.path.join(root, n)).st_blocks * 512
                except OSError:
                    pass
    return total, entries


def run_monitored(
    cmd: Sequence[str],
    out: str,
    watch: Sequence[str] = (),
    interval: float = 5.0,
    disk_interval: float = 60.0,
    timeline: Optional[str] = None,
    label: str = "",
) -> int:
    """Run ``cmd``, write its resources to ``out`` (JSON), return its exit code."""
    sample = os.path.isdir(PROC)
    peak = {"rss": 0, "fds": 0, "bytes": 0, "inodes": 0}
    last = [0, 0]
    stop = threading.Event()
    tl = open(timeline, "w") if timeline else None
    if tl:
        tl.write("epoch\trss_tree_kb\topen_files\tdisk_bytes\tdisk_inodes\n")
    start, t0 = datetime.now(), time.monotonic()
    proc = subprocess.Popen(list(cmd))
    previous = {s: signal.signal(s, lambda n, f: proc.send_signal(n)) for s in (signal.SIGTERM, signal.SIGINT)}

    def sampler() -> None:
        next_disk = 0.0
        while not stop.is_set():
            r = fd = 0
            if sample:
                for p in _tree(proc.pid):
                    r += _rss_kb(p)
                    fd += _nfds(p)
            now = time.monotonic()
            if watch and now >= next_disk:
                last[:] = disk_usage(watch)
                next_disk = now + disk_interval
            peak["rss"], peak["fds"] = max(peak["rss"], r), max(peak["fds"], fd)
            peak["bytes"], peak["inodes"] = max(peak["bytes"], last[0]), max(peak["inodes"], last[1])
            if tl:
                tl.write(f"{int(time.time())}\t{r}\t{fd}\t{last[0]}\t{last[1]}\n")
                tl.flush()
            stop.wait(interval)

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    try:
        _, status, ru = os.wait4(proc.pid, 0)
    finally:
        stop.set()
        th.join(timeout=interval + 5)
        for s, h in previous.items():
            signal.signal(s, h)
        if tl:
            tl.close()
    code = os.waitstatus_to_exitcode(status)
    final = disk_usage(watch) if watch else (0, 0)
    maxrss = ru.ru_maxrss // 1024 if sys.platform == "darwin" else ru.ru_maxrss
    stats = {
        "label": label,
        "command": list(cmd),
        "host": socket.gethostname().split(".")[0],
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "start": start.isoformat(timespec="seconds"),
        "end": datetime.now().isoformat(timespec="seconds"),
        "exit_code": code,
        "wall_s": round(time.monotonic() - t0, 1),
        "cpu_user_s": round(ru.ru_utime, 1),
        "cpu_sys_s": round(ru.ru_stime, 1),
        "peak_rss_max_proc_kb": maxrss,
        "peak_rss_tree_kb": peak["rss"],
        "peak_open_files": peak["fds"],
        "peak_disk_bytes": max(peak["bytes"], final[0]),
        "peak_disk_inodes": max(peak["inodes"], final[1]),
        "final_disk_bytes": final[0],
        "final_disk_inodes": final[1],
        "watch": list(watch),
        "sampled": sample,
        "sample_interval_s": interval,
        "disk_interval_s": disk_interval,
        "nofile_limit": list(resource.getrlimit(resource.RLIMIT_NOFILE)),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = f"{out}.tmp"
    with open(tmp, "w") as f:
        json.dump(stats, f, indent=1)
        f.write("\n")
    os.replace(tmp, out)
    return code


MONITOR_FIELDS = (
    "wall_s", "cpu_user_s", "cpu_sys_s", "peak_rss_max_proc_kb", "peak_rss_tree_kb",
    "peak_open_files", "peak_disk_bytes", "peak_disk_inodes", "final_disk_bytes",
)


def load_monitor(path: str) -> Optional[dict]:
    """The ``MONITOR_FIELDS`` of a monitor file, None when absent or unreadable."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return {k: data.get(k) for k in MONITOR_FIELDS}
