"""Display information about kmhelpers."""

import click

from pykmhelpers import __version__


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
    info = f"""{banner}

📦 Version: {__version__}

📝 Features:
  • Build and manage k-mer indices using kmindex
  • Compose and split indices for flexible data handling
  • Compress indices with configurable parameters
  • Query indices efficiently for sequence analysis
  • Manage index metadata and definitions
  • Support for both presence/absence and abundance indexing

🛠️  Main Commands:
  • build          - Build k-mer indices
  • compose        - Compose indices from sub-indices
  • query          - Query indices with sequences
  • compress       - Compress existing indices
  • list           - List samples and indices

📚 Documentation:
  • Use 'kmhelpers --help' for complete command reference
  • Use 'kmhelpers <command> --help' for command-specific help
  • Visit the project repository for detailed documentation

🔗 Project:
  kmhelpers is designed to simplify k-mer index operations
  and provide a high-level Python interface to kmindex.
"""
    click.echo(info)
