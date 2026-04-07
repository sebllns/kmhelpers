#!/usr/bin/env python3
"""
Unified CLI for kmhelpers - a toolkit for managing, compressing, and querying k-mer indices.
"""

import datetime
import logging
import os
import traceback

import click

from pykmhelpers import Bin, Main, __version__

# Import all groups and commands
from pykmhelpers.cli.about import about
from pykmhelpers.cli.apply import apply
from pykmhelpers.cli.build_subindex import build_subindex
from pykmhelpers.cli.compose import compose
from pykmhelpers.cli.compress import kmindex_compress
from pykmhelpers.cli.count_kmers import count_kmers

# Import experimental commands
from pykmhelpers.cli.exp_compression import exp_compress
from pykmhelpers.cli.experimental import experimental
from pykmhelpers.cli.fof import fof
from pykmhelpers.cli.kmindex import kmindex
from pykmhelpers.cli.list import list_samples
from pykmhelpers.cli.merge_def_files import merge_def_files
from pykmhelpers.cli.merge_span import merge_span
from pykmhelpers.cli.query import query
from pykmhelpers.cli.registry import registry
from pykmhelpers.cli.test import test
from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox


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
        except (click.ClickException, click.exceptions.Exit, SystemExit):
            # Let Click exceptions and sys.exit pass through
            raise
        except Exception as e:
            # Log all other exceptions as CRITICAL
            logger = logging.getLogger(__name__)
            logger.critical(f"Unhandled exception: {type(e).__name__}", exc_info=True)
            click.echo(f"\nFATAL: {type(e).__name__}: {str(e)}", err=True)

            # Write crash dump with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dump_path = f"kmhelpers_{timestamp}.dump"
            try:
                with open(dump_path, "w") as f:
                    f.write(
                        f"kmhelpers crash dump - {datetime.datetime.now().isoformat()}\n"
                    )
                    f.write("=" * 60 + "\n\n")
                    f.write(f"Exception: {type(e).__name__}: {e}\n\n")
                    f.write("Traceback:\n")
                    traceback.print_exc(file=f)
                click.echo(f"Crash dump written to: {dump_path}", err=True)
            except Exception:
                pass

            ctx.exit(1)


@click.command(
    cls=SectionedGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version=__version__, prog_name="kmhelpers")
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity: -v for INFO, -vv for DEBUG",  # TODO , -vvv for TRACE
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    help="Decrease verbosity: -q for ERROR, -qq for CRITICAL,",
)
@click.option(
    "--no-formatting",
    envvar="KMHELPERS_WITHOUT_FORMATTING",
    is_flag=True,
    help="Disable log formatter",
)
@click.option(
    "--log-file",
    envvar="KMHELPERS_LOG_FILE",
    type=click.Path(),
    default=None,
    help="Path to log file (logs will be written in addition to console output)",
)
@click.option(
    "--init-path",
    envvar="KMHELPERS_WITH_INIT",
    is_flag=True,
    default=False,
    help="Initialize environment paths and check for required binaries",
)
@click.option(
    "--bin-path",
    envvar="KMHELPERS_BIN_DIR",
    type=click.Path(file_okay=False, dir_okay=True),
    default="./bin",
    help="Default path for binary executables (default: ./bin)",
)
@click.option(
    "--check-all",
    envvar="KMHELPERS_WITH_BIN_CHECK",
    is_flag=True,
    default=False,
    help="Check that all required binaries are available in PATH",
)
@click.option(
    "--chdir",
    envvar="KMHELPERS_RUN_DIR",
    type=click.Path(file_okay=False, dir_okay=True),
    required=False,
    help="Change to directory before initialization",
)
@click.option(
    "--force",
    "-f",
    envvar="KMHELPERS_SKIP_CONFIRMATION",
    is_flag=True,
    help="🚩 Skip confirmation prompt when using dangerous options. ⚠️",
)
@click.pass_context
def cli(
    ctx,
    verbose,
    quiet,
    no_formatting,
    log_file,
    init_path,
    bin_path,
    check_all,
    chdir,
    force,
):
    """kmhelpers - A toolkit for managing, compressing, and querying k-mer indices."""
    ctx.ensure_object(dict)
    ctx.obj["force"] = force
    # Configure logging based on verbosity level
    log_levels = {
        0: logging.CRITICAL,  # -qq
        1: logging.ERROR,  # -q
        2: logging.WARNING,  # default
        3: logging.INFO,  # -v
        4: logging.DEBUG,  # -vv
        # 5: logging_TRACE # -vvv
    }

    # TODO
    # Change to
    # logging_TRACE = logging.DEBUG - 1
    # logging.addLevelName(logging_TRACE, "TRACE")
    #    logging.log()
    # Use Log. as interface

    default_level = os.getenv("KMHELPERS_LOG_LEVEL", 2)
    log_level = log_levels.get(
        max(min(default_level + verbose - quiet, 4), 0), logging.ERROR
    )

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

    if not no_formatting:
        formatter = ColoredFormatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
            debug_mode=(log_level == logging.DEBUG),
        )
    else:
        formatter = logging.Formatter(
            "%(levelname)-8s | %(message)s",
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
            if not no_formatting:
                file_formatter = logging.Formatter(
                    log_format,
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            else:
                file_formatter = logging.Formatter(
                    "%(levelname)-8s | %(message)s",
                )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            logger = logging.getLogger(__name__)
            logger.debug(f"Logging to file: {log_file}")
            Log.log_file = Toolbox.get_canonical_path(log_file)
        except Exception as e:
            click.echo(f"Warning: Could not open log file '{log_file}': {e}", err=True)

    if init_path:
        Main.init(default_bin_path=bin_path, check_all=check_all, chdir=chdir)
    elif chdir:
        click.echo(f"cd {chdir}", err=True)
        os.chdir(chdir)
    try:
        Bin.check_kmindex()
    except RuntimeError as e:
        click.echo("Could not find kmindex command in path.", err=True)


# Register main commands
list_samples.section = "Main commands"  # type: ignore[assignment]
cli.add_command(list_samples)
compose.section = "Main commands"  # type: ignore[assignment]
cli.add_command(compose)
apply.section = "Main commands"  # type: ignore[assignment]
cli.add_command(apply)
query.section = "Main commands"  # type: ignore[assignment]
cli.add_command(query)
kmindex_compress.section = "Main commands"  # type: ignore[assignment]
cli.add_command(kmindex_compress)

# Register utilities
count_kmers.section = "Utilities"  # type: ignore[assignment]
cli.add_command(count_kmers)
fof.section = "Utilities"  # type: ignore[assignment]
cli.add_command(fof)
# ! DEPRECATED
# build_subindex.section = "Utilities"  # type: ignore[assignment]
# cli.add_command(build_subindex)
registry.section = "Utilities"  # type: ignore[assignment]
cli.add_command(registry)
kmindex.section = "Utilities"  # type: ignore[assignment]
cli.add_command(kmindex)

# Register other commands
experimental.section = "Other"  # type: ignore[assignment]
cli.add_command(experimental)
test.section = "Other"  # type: ignore[assignment]
cli.add_command(test)
about.section = "Other"  # type: ignore[assignment]
cli.add_command(about)

if __name__ == "__main__":
    cli()
