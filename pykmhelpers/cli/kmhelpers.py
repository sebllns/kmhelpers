#!/usr/bin/env python3
"""
Unified CLI for kmhelpers - a toolkit for managing, compressing, and querying k-mer indices.
"""

import os
import logging
import click
from pykmhelpers import __version__, Main, Bin

# Import all groups and commands
from pykmhelpers.cli.fof import fof
from pykmhelpers.cli.test import test
from pykmhelpers.cli.registry import registry
from pykmhelpers.cli.kmindex import kmindex
from pykmhelpers.cli.query import query
from pykmhelpers.cli.count_kmers import count_kmers
from pykmhelpers.cli.compose import compose
from pykmhelpers.cli.build import build
from pykmhelpers.cli.compress import kmindex_compress
from pykmhelpers.cli.experimental import experimental

# Import experimental commands
from pykmhelpers.cli.exp_compression import exp_compress
from pykmhelpers.cli.project import project


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output based on log level."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[2m",  # Dimmed
        "INFO": "\033[0m",  # Normal (reset)
        "WARNING": "\033[33m",  # Dark yellow
        "ERROR": "\033[1;31m",  # Bold red
        "RESET": "\033[0m",  # Reset
        "DIMMED_RED": "\033[2;31m",  # Dimmed red for stacktraces
    }

    def __init__(self, *args, debug_mode=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug_mode = debug_mode

    def format(self, record):
        # Get the color for this log level
        color = self.COLORS.get(record.levelname, self.COLORS["INFO"])
        reset = self.COLORS["RESET"]

        # Save exc_info and clear it temporarily to format main message without traceback
        exc_info = record.exc_info
        record.exc_info = None

        # Format the message
        formatted = super().format(record)

        # Apply color to the entire line
        colored_line = f"{color}{formatted}{reset}"

        # Handle exception info if present and debug mode
        if exc_info and self.debug_mode:
            exc_color = self.COLORS["DIMMED_RED"]
            exc_reset = self.COLORS["RESET"]
            try:
                exc_text = self.formatException(exc_info)
                colored_line += f"\n{exc_color}{exc_text}{exc_reset}"
            except Exception:
                pass

        return colored_line


class SectionedGroup(click.Group):
    """Custom Group that organizes commands into sections."""

    def format_commands(self, ctx, formatter):
        """Format commands organized by sections."""
        sections = {}

        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None:
                continue

            # Get section from command attribute, default to "Commands"
            section = getattr(cmd, "section", "Commands")
            if section not in sections:
                sections[section] = []

            help_text = cmd.get_short_help_str(limit=100)
            sections[section].append((subcommand, help_text))

        # Define section order
        section_order = ["Main commands", "Utilities", "Advanced", "Other"]

        # Write sections in defined order
        for section in section_order:
            if section in sections:
                with formatter.section(section):
                    formatter.write_dl(sections[section])

    def invoke(self, ctx):
        """Invoke the group with global exception handling."""
        try:
            return super().invoke(ctx)
        except (click.ClickException, SystemExit):
            # Let Click exceptions and sys.exit pass through
            raise
        except Exception as e:
            # Log all other exceptions as CRITICAL
            logger = logging.getLogger(__name__)
            logger.critical(f"Unhandled exception: {type(e).__name__}", exc_info=True)
            click.echo(f"\nFATAL: {type(e).__name__}: {str(e)}", err=True)
            ctx.exit(1)


@click.command(
    cls=SectionedGroup, context_settings={"help_option_names": ["-h", "--help"]}
)
@click.version_option(version=__version__, prog_name="kmhelpers")
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity: -v for WARNING, -vv for INFO, -vvv for DEBUG",
)
@click.option(
    "--log-file",
    type=click.Path(),
    default=None,
    help="Path to log file (logs will be written in addition to console output)",
)
@click.option(
    "--init-path",
    is_flag=True,
    default=False,
    help="Initialize environment paths and check for required binaries",
)
@click.option(
    "--bin-path",
    type=click.Path(file_okay=False, dir_okay=True),
    default="./bin",
    help="Default path for binary executables (default: ./bin)",
)
@click.option(
    "--check-all",
    is_flag=True,
    default=True,
    help="Check that all required binaries are available in PATH",
)
@click.option(
    "--chdir",
    type=click.Path(file_okay=False, dir_okay=True),
    default="",
    help="Change to directory before initialization",
)
def cli(verbose, log_file, init_path, bin_path, check_all, chdir):
    """kmhelpers - A toolkit for managing, compressing, and querying k-mer indices."""
    # Configure logging based on verbosity level
    log_levels = {
        0: logging.ERROR,  # default
        1: logging.WARNING,  # -v
        2: logging.INFO,  # -vv
        3: logging.DEBUG,  # -vvv
    }
    log_level = log_levels.get(min(verbose, 3), logging.ERROR)

    # Configure root logger with different format for debug level
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
        if log_level == logging.DEBUG
        else "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Create console handler with colored formatter
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter = ColoredFormatter(
        log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        debug_mode=(log_level == logging.DEBUG),
    )
    console_handler.setFormatter(formatter)

    # Remove any existing handlers and add the new one
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # Add file handler if log file path is provided
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, mode="w")
            file_handler.setLevel(log_level)
            # Use plain formatter for file (no colors)
            file_formatter = logging.Formatter(
                log_format,
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            logger = logging.getLogger(__name__)
            logger.debug(f"Logging to file: {log_file}")
        except Exception as e:
            click.echo(f"Warning: Could not open log file '{log_file}': {e}", err=True)

    if init_path:
        Main.init(default_bin_path=bin_path, check_all=check_all, chdir=chdir)
    elif chdir:
        logging.info(f"cd {chdir}")
        os.chdir(chdir)
    try:
        Bin.check_kmindex()
    except RuntimeError as e:
        click.echo("Could not fin kmindex command in path.", err=True)
        click.echo(e, err=True)


# Register main commands
compose.section = "Main commands"
cli.add_command(compose)
build.section = "Main commands"
cli.add_command(build)
query.section = "Main commands"
cli.add_command(query)
kmindex_compress.section = "Main commands"
cli.add_command(kmindex_compress)

# Register utilities
count_kmers.section = "Utilities"
cli.add_command(count_kmers)
fof.section = "Utilities"
cli.add_command(fof)
registry.section = "Utilities"
cli.add_command(registry)
kmindex.section = "Utilities"
cli.add_command(kmindex)

# Register other commands
experimental.section = "Other"
cli.add_command(experimental)
test.section = "Other"
cli.add_command(test)


if __name__ == "__main__":
    cli()
