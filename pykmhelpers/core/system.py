"""Helpers for inspecting and adjusting process resource limits (ulimits)."""

import resource


def get_ulimit(resource_type=resource.RLIMIT_NOFILE):
    """Return the (soft, hard) ulimit values for the given resource type."""
    return resource.getrlimit(resource_type)


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
