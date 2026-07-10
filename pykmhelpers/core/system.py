"""Helpers for inspecting and adjusting process resource limits (ulimits)."""

import os
import resource

import psutil


def get_ulimit(resource_type=resource.RLIMIT_NOFILE):
    """Return the (soft, hard) ulimit values for the given resource type."""
    return resource.getrlimit(resource_type)


def get_available_ram(safety_margin: float = 0.9) -> int:
    """Return usable RAM in bytes: currently available memory scaled down by `safety_margin`."""
    return int(psutil.virtual_memory().available * safety_margin)


def get_available_threads(safety_margin: float = 0.9) -> int:
    """Return a safe thread count: `os.cpu_count()` scaled down by `safety_margin`."""
    return max(1, int((os.cpu_count() or 1) * safety_margin))


def get_max_open_files(safety_margin: float = 0.9) -> int:
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
