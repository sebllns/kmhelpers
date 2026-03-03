"""Display information about kmhelpers."""

import click

from pykmhelpers import __version__


def get_banner():
    """Get the banner with optional terminal graphics for compatible terminals."""
    # Terminal graphics escape sequence for compatible terminals (iTerm2, Kitty, etc.)
    # This will only display in terminals that support inline images
    graphics = ()

    banner = f"""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║              XWWXd;.   XWX      lWW.   ;dXWWX              ║
║              WWWWWWXl  WWW';;dddWWWl l0WWWWWW              ║
║              ldd0WWWWX;WWWWWWWWWWWWk0WWWWXkdl              ║
║                  .lXWWWWWWX00dddWWWWWWWk'                  ║
║                     kWWWWWk;'.  WWWWW0'                    ║
║                      oWWWWWWWWXKWWWWK                      ║
║                       0WWWld00WWWWWW                       ║
║                       lWWW   .;kWWWd                       ║
║                       dWWWdk0WWWWWW0                       ║
║                       WWWWWWWWWXWWWW'                      ║
║                     .KWWWWWOo,. WWWWX,                     ║
║                    lXWWWWWWWW0kdWWWWWWl                    ║
║                 'l0WWWXWWWkXWWWWWWWXWWWXd;.                ║
║              k0XWWWWWd WWW  ';ddWWWllXWWWWW00              ║
║              WWWWW0l'  WWW      0WW;  l0WWWWW              ║
║              lWWx,     xWl      ,WK     ,xWWK              ║
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
