"""Exclusive file locks and atomic replaces, for files several processes
update (the registry: the publish scripts; the layout: ``compose`` and the
publish jobs of ``apply``).

Every lock is a ``flock(2)`` lock, the one the ``flock`` command of the
publish scripts takes: on Linux, ``fcntl``/``lockf`` locks do not see it.
"""

import fcntl
import logging
import os
from typing import Optional

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
            fcntl.flock(self._f, fcntl.LOCK_EX)
        except OSError as e:
            logger.warning(f"Could not lock {self._path} ({e}): writing without a lock")
        return self

    def __exit__(self, *exc) -> None:
        assert self._f is not None
        self._f.close()  # releases the lock


def remove_if_free(path: str) -> Optional[bool]:
    """Remove the lock file ``path`` when no process holds it: True when
    removed, False when it is held (or can't be locked or removed), None
    when there is none.

    The file is removed while locked, so no writer is cut short. A process
    that opened it just before and waits for the lock then locks a removed
    file: callers only remove a lock once nothing should use it any more.
    """
    try:
        f = open(path)  # read-only: flock needs no write, and creates nothing
    except FileNotFoundError:
        return None
    except OSError as e:
        logger.warning(f"Could not open {path} ({e}): kept")
        return False
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        try:
            os.remove(path)
        except FileNotFoundError:
            return None
        except OSError as e:
            logger.warning(f"Could not remove {path} ({e}): kept")
            return False
    return True


def replace_atomically(path: str, text: str) -> None:
    """Write ``text`` to ``path`` through a temporary file renamed over it."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
