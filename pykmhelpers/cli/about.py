"""Display information about kmhelpers."""

import click

from pykmhelpers import __version__
from pykmhelpers.core.constants import KMHELPERS_COMMIT, get_commit_subject


def get_banner():
    banner = f"""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║              OOOOO.....OOO.......OO.....OOOOO              ║
║              OOOOOOO...OOO...OOOOOO...OOOOOOO              ║
║              .OOOOOOOO.OOOOOOOOOOOOOOOOOOOOO.              ║
║              ......OOOOOOOOOOOOOOOOOOOOO.....              ║
║              .......OOOOOOO.....OOOOOO.......              ║
║              ........OOOOOOOOOOOOOOOO........              ║
║              .........OOOO.OOOOOOOOO.........              ║
║              ..........OOO.....OOOOO.........              ║
║              .........OOOOOOOOOOOOOO.........              ║
║              .........OOOOOOOOOOOOOO.........              ║
║              ........OOOOOOOO...OOOOO........              ║
║              .......OOOOOOOOOOOOOOOOOO.......              ║
║              .....OOOOOOOOOOOOOOOOOOOOOOO....              ║
║              OOOOOOOOO.OOO....OOOOO..OOOOOOOO              ║
║              OOOOOO....OOO......OOO....OOOOOO              ║
║              .OOO......OO........OO......OOOO              ║
║                                                            ║
║              kmhelpers - k-mer Index Toolkit               ║
║                                                            ║
║   A comprehensive toolkit for managing, compressing, and   ║
║   querying k-mer indices with support for large-scale      ║
║   genomic data analysis.                                   ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝"""

    return banner


@click.command()
def about():
    """Display information about kmhelpers and its components."""
    banner = get_banner()
    commit = ""
    if KMHELPERS_COMMIT != "UNKNOWN":
        subject = get_commit_subject()
        commit = f"\n🔖 Commit:  {KMHELPERS_COMMIT}"
        if subject:
            commit += f" -- {subject}"
    info = f"""{banner}

📦 Version: {__version__}{commit}

📝 Features:
  • Build and manage k-mer indices using kmindex
  • Compose and split indices for flexible data handling
  • Compress indices with configurable parameters
  • Query indices efficiently for sequence analysis
  • Manage index metadata and definitions

📚 Documentation:
  • Use 'kmhelpers --help' for complete command reference
  • Use 'kmhelpers <command> --help' for command-specific help
  • https://sebllns.github.io/kmhelpers for detailed documentation

🔗 Project:
  kmhelpers is designed to simplify k-mer index operations
  and provide a high-level Python interface to kmindex.

🧩 Third-party tools:
  • kmindex   https://github.com/tlemane/kmindex
  • kmtricks  https://github.com/tlemane/kmtricks
  • ntCard    https://github.com/bcgsc/ntCard
  • click     https://click.palletsprojects.com
"""
    click.echo(info)
