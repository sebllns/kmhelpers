import os
import subprocess
from pathlib import Path

from pykmhelpers import __version__

KMHELPERS_VERSION = __version__


def get_commit() -> str:
    """Return the short git commit of this source tree, or "UNKNOWN".

    Anchored to the package directory so it reports the commit kmhelpers was
    installed from, not whatever repo the user happens to run inside. Non-git
    installs (e.g. pip) fall back to "UNKNOWN".
    """
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).resolve().parent,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            or "UNKNOWN"
        )
    except Exception:
        return "UNKNOWN"


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
