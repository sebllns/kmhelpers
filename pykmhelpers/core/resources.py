"""Helpers for inspecting and adjusting process resource limits (ulimits)."""

import logging
import os
import resource

import psutil

logger = logging.getLogger(__name__)

# Open-files ceiling used for sizing when the hard limit is unlimited
NOFILE_CEILING = 1_048_576


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
    """Return a safe open-files ceiling: the hard RLIMIT_NOFILE scaled down by `safety_margin`.

    The hard limit, not the soft one: ``maximize_nofile`` raises the soft limit
    to it before anything is run (CLI start, kmtricks and kmindex calls, and
    the generated scripts). An unlimited hard limit counts as ``NOFILE_CEILING``.
    """
    _, hard = get_ulimit(resource.RLIMIT_NOFILE)
    if hard == resource.RLIM_INFINITY:
        hard = NOFILE_CEILING
    return max(1, int(hard * safety_margin))


def maximize_nofile() -> int:
    """Raise the open-files (RLIMIT_NOFILE) limit to the highest allowed value.

    Returns the soft limit in effect afterwards. A failure is logged, not
    raised: the process keeps its current limit.
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    try:
        resource.setrlimit(
            resource.RLIMIT_NOFILE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        )
    except ValueError:
        # Not root: raise soft to hard limit only
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        except (ValueError, OSError) as e:
            logger.warning(
                f"Could not raise the open-files limit from {soft} to {hard}: {e}; "
                f"sizing assumes {hard}"
            )
            return soft
    new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if new_soft == soft:
        logger.debug(f"open files: soft already at hard ({soft})")
    else:
        logger.debug(f"open files: soft {soft} -> {new_soft} (hard {new_hard})")
    return new_soft


if __name__ == "__main__":
    print(f"Available RAM: {get_available_ram():,} bytes")
    print(f"Available threads: {get_available_threads():,}")
    print(f"Max open files: {get_max_open_files():,}")
