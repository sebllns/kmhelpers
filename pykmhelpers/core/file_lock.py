"""Exclusive file locks and atomic replaces, for files several processes
update (the layout: ``compose`` and the publish jobs of ``apply``)."""

import fcntl
import logging
import os

logger = logging.getLogger(__name__)


class locked:
    """Exclusive lock on ``path`` (created if needed), held in a ``with``
    block. Where the filesystem has no locks, it goes on without: writers
    replace files atomically, so a file stays whole, and callers redo a lost
    update on their next run."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._f = None

    def __enter__(self) -> "locked":
        self._f = open(self._path, "a")
        try:
            fcntl.lockf(self._f, fcntl.LOCK_EX)
        except OSError as e:
            logger.warning(f"Could not lock {self._path} ({e}): writing without a lock")
        return self

    def __exit__(self, *exc) -> None:
        assert self._f is not None
        self._f.close()  # releases the lock


def replace_atomically(path: str, text: str) -> None:
    """Write ``text`` to ``path`` through a temporary file renamed over it."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
