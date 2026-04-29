import argparse
import json
import logging
import os

import diskbench
import fiobench

logger = logging.getLogger(__name__)


def _get_fstype(path):
    real = os.path.realpath(path)
    best_match = ""
    fstype = ""
    with open("/proc/mounts") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3 and real.startswith(parts[1]):
                if len(parts[1]) > len(best_match):
                    best_match = parts[1]
                    fstype = parts[2]
    return fstype


# We used a 4k block size (--bs=4k) to better reflect kmindex’s access pattern. Since the index is accessed via mmap, each operation typically corresponds to reading a memory page, which is 4k in the vast majority of cases. This makes IOPS and latency particularly critical for our workload.
def disk_benchmark(path, mode="both", size_mb=10240, block_kb=4):
    fstype = _get_fstype(os.path.dirname(os.path.abspath(path)))
    if fstype == "tmpfs":
        logger.warning(f"Path is on tmpfs: benchmark measures RAM speed, not disk")
    if mode in ("write", "both") and os.path.exists(path):
        raise FileExistsError(f"Path already exists: {path}")
    try:
        wrapper = fiobench.FioWrapper()
        logger.info("fio available, using FioWrapper")
        return wrapper.run(path, mode=mode, size=f"{size_mb}M", runtime="30s")
    except FileNotFoundError:
        logger.info("fio not found, falling back to diskbench")
        return diskbench.run(path, mode, size_mb, block_kb, zero=False)
    finally:
        if mode in ("write", "both") and os.path.exists(path):
            os.remove(path)


def main():
    parser = argparse.ArgumentParser(
        description="Disk benchmark (fio if available, else diskbench)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f", "--filename", default="/tmp/bench.tmp", help="Path to test file"
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["read", "write", "both"],
        default="both",
        help="Benchmark mode",
    )
    parser.add_argument("-s", "--size", type=int, default=10240, help="Data size in MB")
    parser.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=4,
        help="Block size in KB (diskbench fallback only)",
    )
    parser.add_argument(
        "-j", "--json", metavar="FILE", help="Write results to JSON file"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)-8s | %(message)s")

    results = disk_benchmark(
        args.filename, mode=args.mode, size_mb=args.size, block_kb=args.block_size
    )

    for key, value in results.items():
        logger.info(f"  {key}: {value}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results written to {args.json}")


if __name__ == "__main__":
    main()
