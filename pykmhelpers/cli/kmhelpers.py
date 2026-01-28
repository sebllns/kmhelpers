#!/usr/bin/env python3
"""
Unified CLI for kmhelpers - a toolkit for managing, compressing, and querying k-mer indices.
"""

import os
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
            section = getattr(cmd, 'section', 'Commands')
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


@click.command(cls=SectionedGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="kmhelpers")
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
def cli(init_path, bin_path, check_all, chdir):
    """kmhelpers - A toolkit for managing, compressing, and querying k-mer indices."""
    if init_path:
        Main.init(default_bin_path=bin_path, check_all=check_all, chdir=chdir)
    elif chdir:
        print(f"cd {chdir}")
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
