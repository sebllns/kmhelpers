#!/usr/bin/env python3
"""
fiobench.py - fio-based random read/write benchmark

Usage:
    python fiobench.py -f fio.tmp --mode both
    python fiobench.py -f fio.tmp --mode write
    python fiobench.py -f fio.tmp --mode read --size 10G
"""

import argparse
import json
import logging

from pykmhelpers.core.wrapper import Wrapper

logger = logging.getLogger(__name__)


COMMON_ARGS = [
    "--bs=4k",
    "--ioengine=posixaio",
    "--direct=1",
    "--iodepth=64",
    "--numjobs=8",
    "--group_reporting",
    "--time_based",
    "--output-format=json",
]


def _extract(job, rw_key):
    stats = job[rw_key]
    return {
        "iops": stats["iops"],
        "iops_mean": stats["iops_mean"],
        "bw_kb_s": stats["bw"],
        "bw_mean_kb_s": stats["bw_mean"],
        "lat_ns_mean": stats["lat_ns"]["mean"],
        "lat_ns_stddev": stats["lat_ns"]["stddev"],
    }


class FioWrapper(Wrapper):
    def __init__(self, dry_run: bool = False) -> None:
        super().__init__("fio", dry_run)

    def _run_fio(self, name, rw, filename, size, runtime):
        cmd = [
            self.which,
            f"--name={name}",
            f"--rw={rw}",
            f"--size={size}",
            f"--filename={filename}",
            f"--runtime={runtime}",
        ] + COMMON_ARGS
        result = self._run_cmd(cmd)
        if self.dry_run or not result.stdout:
            return None
        return json.loads(result.stdout)["jobs"][0]

    def run(self, filename, mode="both", size="50G", runtime="60s"):
        if mode not in ("read", "write", "both"):
            raise ValueError(f"mode must be 'read', 'write', or 'both', got {mode!r}")

        results = {}

        if mode in ("write", "both"):
            logger.info("Running random write benchmark...")
            job = self._run_fio("rand-write", "randwrite", filename, size, runtime)
            if job is not None:
                results["write"] = _extract(job, "write")

        if mode in ("read", "both"):
            logger.info("Running random read benchmark...")
            job = self._run_fio("rand-read", "randread", filename, size, runtime)
            if job is not None:
                results["read"] = _extract(job, "read")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="fio random read/write benchmark",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f", "--filename", default="fio.tmp", help="Path to fio test file"
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["read", "write", "both"],
        default="both",
        help="Benchmark mode",
    )
    parser.add_argument("-s", "--size", default="50G", help="File size (e.g. 50G, 10G)")
    parser.add_argument(
        "-r", "--runtime", default="60s", help="Benchmark duration (e.g. 60s, 30s)"
    )
    parser.add_argument(
        "-j", "--json", metavar="FILE", help="Write results to JSON file"
    )
    args = parser.parse_args()

    try:
        wrapper = FioWrapper()
    except FileNotFoundError as e:
        logger.error(str(e))
        raise SystemExit(1)

    results = wrapper.run(
        args.filename, mode=args.mode, size=args.size, runtime=args.runtime
    )

    for rw, stats in results.items():
        logger.info(f"[{rw.upper()}]")
        logger.info(
            f"  IOPS:          {stats['iops']:.0f}  (mean: {stats['iops_mean']:.0f})"
        )
        logger.info(
            f"  Bandwidth:     {stats['bw_kb_s'] / 1024:.1f} MB/s  (mean: {stats['bw_mean_kb_s'] / 1024:.1f} MB/s)"
        )
        logger.info(
            f"  Latency mean:  {stats['lat_ns_mean'] / 1000:.1f} µs  (stddev: {stats['lat_ns_stddev'] / 1000:.1f} µs)"
        )

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results written to {args.json}")


if __name__ == "__main__":
    main()
