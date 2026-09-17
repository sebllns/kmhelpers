"""Check that external tools are callable."""

import logging
import subprocess

import click

from pykmhelpers.core.wrapper import Wrapper

logger = logging.getLogger(__name__)

TOOLS = ["kmindex", "kmtricks", "ntcard"]


def get_version(path: str) -> str:
    """Return the first line printed by `path --version`."""
    # Return code is ignored: kmtricks --version exits with 1
    result = subprocess.run(
        [path, "--version"], capture_output=True, text=True, timeout=10
    )
    output = (result.stdout + result.stderr).strip()
    return output.splitlines()[0].strip() if output else "unknown version"


@click.command(name="check-deps")
def check_deps():
    """Check that kmindex, kmtricks and ntcard are callable.

    \b
    For each tool, show its path and version, or a warning if not found.
    A <TOOL>_BIN_PATH environment variable (e.g. KMINDEX_BIN_PATH) takes
    precedence over PATH.
    """
    for tool in TOOLS:
        try:
            path = Wrapper(tool).which
            version = get_version(path)
        except (FileNotFoundError, OSError, subprocess.SubprocessError) as e:
            logger.warning(f"{tool:<10} {e}")
            continue
        logger.info(f"{tool:<10} {version:<20} {path}")
