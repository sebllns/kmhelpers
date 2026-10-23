"""Resource usage of a kmtricks run, read back from its ``kmtricks.log``.

The log is written by ``Wrapper._run_cmd`` (``core/wrapper.py``) when ``apply``
runs kmtricks itself: a header with the monitored execution time, CPU and
memory, then the kmtricks stderr. Runs built by the exported shell scripts
write no such log.
"""

import os
import re
from datetime import datetime

_HEADER = {
    "duration_s": re.compile(r"^Execution time: ([\d.]+)s$", re.M),
    "max_cpu_pct": re.compile(r"^Max CPU: ([\d.]+)%$", re.M),
    "max_memory_mb": re.compile(r"^Max Memory: ([\d.]+) MB$", re.M),
    "return_code": re.compile(r"^Return code: (-?\d+)$", re.M),
}
_STAMP = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:\.\d+)?\]", re.M)
_SAMPLES = re.compile(r"(\d+) samples found \((\d+) read files\)")
_PARTITIONS = re.compile(r"Use (\d+) partitions")
_PEAK = re.compile(r"Done in \S+ - Peak RSS -> ([\d.]+) MB")


def parse_kmtricks_log(path: str) -> dict:
    """What ``path`` tells about its run; empty when there is no log.

    Never raises: a partial log (failed run) gives only the fields it has.
    ``peak_rss_mb`` is the peak kmtricks reports itself, else the one sampled
    by the wrapper.
    """
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return {}

    info: dict = {}
    for key, pattern in _HEADER.items():
        m = pattern.search(text)
        if m:
            info[key] = int(m.group(1)) if key == "return_code" else float(m.group(1))

    stamps = _STAMP.findall(text)
    if stamps:
        info["started"] = _iso(stamps[0])
        info["finished"] = _iso(stamps[-1])
    if m := _SAMPLES.search(text):
        info["samples"] = int(m.group(1))
        info["read_files"] = int(m.group(2))
    if m := _PARTITIONS.search(text):
        info["partitions"] = int(m.group(1))

    peak = _PEAK.search(text)
    if peak:
        info["peak_rss_mb"] = float(peak.group(1))
    elif "max_memory_mb" in info:
        info["peak_rss_mb"] = info["max_memory_mb"]
    info.pop("max_memory_mb", None)
    return info


def run_log_path(log_dir: str, run: str) -> str:
    """``kmtricks.log`` of the run ``run``, as ``IndexBuilder`` writes it."""
    return os.path.join(log_dir, run, "kmtricks.log")


def _iso(stamp: str) -> str:
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").isoformat()
