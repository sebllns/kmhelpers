import os
import subprocess
from pathlib import Path

from pykmhelpers import __version__

KMHELPERS_VERSION = __version__


def _git(*args: str) -> str:
    """Run git in the package directory, return its stripped output or ""."""
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=Path(__file__).resolve().parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def get_commit() -> str:
    """Return the short git commit of this source tree, or "UNKNOWN".

    Anchored to the package directory so it reports the commit kmhelpers was
    installed from, not whatever repo the user happens to run inside. Non-git
    installs (e.g. pip) fall back to "UNKNOWN".
    """
    return _git("rev-parse", "--short", "HEAD") or "UNKNOWN"


def get_commit_subject() -> str:
    """Return the subject line of the current commit, or "" if not found."""
    return _git("log", "-1", "--format=%s")


KMHELPERS_COMMIT = get_commit()

DATA_EXT = (
    # ".fasta.gz",
    # ".fastq.gz",
    # ".fa.gz",
    # ".fq.gz",
    # ".fna.gz",
    ".fasta",
    ".fastq",
    ".fa",
    ".fq",
    ".fna",
)

COMPRESS_EXT = (".gz", ".bz2", ".zip", ".xz", ".zst")

# Data extensions, plain and compressed. Compressed variants come first so
# suffix matching strips the full extension (".fa.gz" before ".fa").
DATA_EXT_ALL = (
    tuple(f"{ext}{comp}" for ext in DATA_EXT for comp in COMPRESS_EXT) + DATA_EXT
)


def strip_data_ext(fname: str) -> str:
    """Remove trailing compression suffixes (possibly stacked), then one data
    extension. Otherwise fall back to removing the last suffix."""
    base = fname
    while base.endswith(COMPRESS_EXT):
        base = base[: base.rfind(".")]
    for ext in DATA_EXT:
        if base.endswith(ext):
            return base[: -len(ext)]
    return os.path.splitext(fname)[0]
