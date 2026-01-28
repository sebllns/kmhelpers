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
from pykmhelpers.cli.experimental import experimental

# Import experimental commands
from pykmhelpers.cli.compression import compress
from pykmhelpers.cli.project import project


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
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


# Register all groups
cli.add_command(fof)
cli.add_command(test)
cli.add_command(registry)
cli.add_command(experimental)
cli.add_command(kmindex)

# Register all standalone commands
cli.add_command(query)
cli.add_command(count_kmers)
cli.add_command(compose)
cli.add_command(build)


if __name__ == "__main__":
    cli()
