#!/usr/bin/env python3
"""
diskbench.py - simple sequential read/write disk benchmark

Usage:
    python diskbench.py -f /scratch/test.tmp -s 4096 -b 1024
    python diskbench.py -f /scratch/test.tmp -s 4096 -b 1024 --zero
"""

import argparse
import ctypes
import json
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
POSIX_FADV_DONTNEED = 4


def _fadvise_dontneed(fd, offset, length):
    ret = _libc.posix_fadvise(
        fd, ctypes.c_int64(offset), ctypes.c_int64(length), POSIX_FADV_DONTNEED
    )
    if ret != 0:
        logger.debug(f"posix_fadvise failed: {ret}")


def _drop_caches(fd=None, length=None):
    if os.getuid() == 0:
        try:
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("1\n")
            logger.debug("Dropped page cache")
        except OSError as e:
            logger.debug(f"drop_caches failed: {e}")
    elif fd is not None and length is not None:
        logger.debug("Not root, falling back to posix_fadvise")
        _fadvise_dontneed(fd, 0, length)
    else:
        logger.debug("Skipping cache drop: not root and no fd provided")
    # with open("/proc/meminfo") as f:
    #     info = {
    #         k: int(v.split()[0]) // 1024
    #         for line in f
    #         for k, v in [line.split(":", 1)]
    #         if k in ("MemFree", "Cached", "Dirty")
    #     }
    # print(
    #     f"ret={ret} MemFree={info.get('MemFree')}MB Cached={info.get('Cached')}MB Dirty={info.get('Dirty')}MB"
    # )


def aligned_buffer(size, alignment=4096):
    """Allocate a buffer aligned to `alignment` bytes, required by O_DIRECT."""
    buf = (ctypes.c_char * (size + alignment))()
    offset = alignment - (ctypes.addressof(buf) % alignment)
    return (ctypes.c_char * size).from_buffer(buf, offset)


def open_direct(path, flags):
    """Open file with O_DIRECT if available, fallback to normal open with warning."""
    try:
        return os.open(path, flags | os.O_DIRECT, 0o600)
    except AttributeError:
        logger.warning(
            "O_DIRECT not available on this platform, results may include cache effects"
        )
        return os.open(path, flags, 0o600)


def write_test(path, total_mb, block_kb, zero=False, show_progress=True):
    """
    Sequential write test.
    Returns (throughput_mb_s, elapsed_s).
    block_kb: block size in KB (must be multiple of 512 for O_DIRECT alignment).
    zero: fill buffer with zeros instead of random data.
    """
    block_size = block_kb * 1024
    total_bytes = total_mb * 1024 * 1024
    n_blocks = total_bytes // block_size

    buf = aligned_buffer(block_size)
    if not zero:
        ctypes.memmove(buf, os.urandom(block_size), block_size)
    # zero buffer is already zeroed by ctypes

    fd = open_direct(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
    start = time.perf_counter()
    written = 0
    for i in range(n_blocks):
        os.write(fd, buf)
        written += block_size
        if show_progress:
            sys.stdout.write(f"\rWrite: {(i + 1) * 100 // n_blocks:3d}%")
            sys.stdout.flush()
    os.fsync(fd)
    elapsed = time.perf_counter() - start
    os.close(fd)

    if show_progress:
        print()

    return written / 1024 / 1024 / elapsed, elapsed


def read_test(path, total_mb, block_kb, show_progress=True):
    """
    Sequential read test.
    Returns (throughput_mb_s, elapsed_s).
    """
    block_size = block_kb * 1024
    total_bytes = total_mb * 1024 * 1024
    n_blocks = total_bytes // block_size

    buf = aligned_buffer(block_size)
    fd = open_direct(path, os.O_RDONLY)
    start = time.perf_counter()
    read_bytes = 0
    for i in range(n_blocks):
        n = os.readv(fd, [buf])
        if not n:
            break
        read_bytes += n
        if show_progress:
            sys.stdout.write(f"\rRead:  {(i + 1) * 100 // n_blocks:3d}%")
            sys.stdout.flush()
    elapsed = time.perf_counter() - start
    os.close(fd)

    if show_progress:
        print()

    return read_bytes / 1024 / 1024 / elapsed, elapsed


def run(path, mode, total_mb, block_kb, zero):
    if mode not in ("read", "write", "both"):
        raise ValueError(f"mode must be 'read', 'write', or 'both', got {mode!r}")

    actual_size = (total_mb * 1024 // block_kb) * block_kb // 1024
    result = {"file": path, "size_mb": actual_size, "block_size_kb": block_kb}

    if mode in ("write", "both"):
        result["buffer"] = "zeros" if zero else "random"
        os.sync()
        write_mbps, write_s = write_test(path, actual_size, block_kb, zero=zero)
        result["write_mb_s"] = round(write_mbps, 2)
        result["write_elapsed_s"] = round(write_s, 2)

    if mode in ("read", "both"):
        os.sync()
        fd = os.open(path, os.O_RDONLY)
        try:
            _drop_caches(fd=fd, length=actual_size * 1024 * 1024)
        finally:
            os.close(fd)
        read_mbps, read_s = read_test(path, actual_size, block_kb)
        result["read_mb_s"] = round(read_mbps, 2)
        result["read_elapsed_s"] = round(read_s, 2)

    return result


def get_args():
    parser = argparse.ArgumentParser(
        description="Sequential disk read/write benchmark",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--file",
        default="/tmp/diskbench.tmp",
        help="Path to test file (will be overwritten)",
    )
    parser.add_argument(
        "-s", "--size", type=int, default=1024, help="Total data size to write in MB"
    )
    parser.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=1024,
        help="Block size in KB (must be multiple of 512 for O_DIRECT)",
    )
    parser.add_argument(
        "-j", "--json", metavar="FILE", help="Write results to JSON file"
    )
    parser.add_argument(
        "--zero",
        action="store_true",
        help="Fill write buffer with zeros instead of random data",
    )
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Keep test file after benchmark"
    )
    return parser.parse_args()


def main():
    args = get_args()

    if (args.block_size * 1024) % 512 != 0:
        print(
            "Error: block size must be a multiple of 512 bytes for O_DIRECT alignment",
            file=sys.stderr,
        )
        sys.exit(1)

    actual_size = (args.size * 1024 // args.block_size) * args.block_size // 1024
    buf_type = "zeros" if args.zero else "random"
    print(f"File:       {args.file}")
    print(
        f"Size:       {actual_size} MB  (block size: {args.block_size} KB, buffer: {buf_type})"
    )
    print()

    os.sync()
    write_mbps, write_s = write_test(
        args.file, actual_size, args.block_size, zero=args.zero
    )
    os.sync()
    read_mbps, read_s = read_test(args.file, actual_size, args.block_size)

    print(f"\nWrite: {write_mbps:8.1f} MB/s  ({write_s:.2f} s)")
    print(f"Read:  {read_mbps:8.1f} MB/s  ({read_s:.2f} s)")

    if args.json:
        result = {
            "file": args.file,
            "size_mb": actual_size,
            "block_size_kb": args.block_size,
            "buffer": buf_type,
            "write_mb_s": round(write_mbps, 2),
            "write_elapsed_s": round(write_s, 2),
            "read_mb_s": round(read_mbps, 2),
            "read_elapsed_s": round(read_s, 2),
        }
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults written to {args.json}")

    if not args.no_cleanup:
        os.remove(args.file)


if __name__ == "__main__":
    main()
