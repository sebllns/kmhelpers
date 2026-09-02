"""Helpers for inspecting and adjusting process resource limits (ulimits)."""

import os
import resource

import psutil


def get_ulimit(resource_type=resource.RLIMIT_NOFILE):
    """Return the (soft, hard) ulimit values for the given resource type."""
    return resource.getrlimit(resource_type)


def get_available_ram(safety_margin: float = 1.0) -> int:
    """Return usable RAM in bytes: currently available memory scaled down by `safety_margin`."""
    rss_limit, _ = get_ulimit(resource.RLIMIT_RSS)
    available_ram = psutil.virtual_memory().available
    usable_ram = rss_limit if 0 < rss_limit < available_ram else available_ram
    if usable_ram <= 0:
        raise ValueError("could not determine available RAM")
    return int(usable_ram * safety_margin)


def get_available_threads(safety_margin: float = 1.0) -> int:
    """Return a safe thread count: CPUs available to this process, scaled down by `safety_margin`."""
    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        # sched_getaffinity is Linux-only
        cpu_count = os.cpu_count() or 1
    return max(1, int(cpu_count * safety_margin))


def get_max_open_files(safety_margin: float = 1.0) -> int:
    """Return a safe open-files ceiling: the soft RLIMIT_NOFILE scaled down by `safety_margin`."""
    soft, _ = get_ulimit(resource.RLIMIT_NOFILE)
    return max(1, int(soft * safety_margin))


def maximize_nofile():
    """Raise the open-files (RLIMIT_NOFILE) limit to the highest allowed value."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    try:
        resource.setrlimit(
            resource.RLIMIT_NOFILE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        )
    except ValueError:
        # Not root: raise soft to hard limit only
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))


if __name__ == "__main__":
    print(f"Available RAM: {get_available_ram()} bytes")
    print(f"Available threads: {get_available_threads()}")
    print(f"Max open files: {get_max_open_files()}")
