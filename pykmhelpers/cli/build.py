"""Build k-mer index command."""

import click
import os
import traceback
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.index_db import IndexDefinitionTools, IndexTable, Index
from pykmhelpers.cli.shared import estimate_build_size


@click.command()
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--workdir",
    "-w",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output directory path (created if doesn't exist)",
)
@click.option(
    "--rootpath",
    "-r",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Base path to resolve relative sample paths. By default, relative \
paths are resolved from the run directory; use this option if you \
need to resolve them from a different location.",
)
@click.option(
    "--select-ids",
    "-s",
    multiple=True,
    help="Build only selected IDs (comma-separated or multiple -s)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="Number of threads (default: 1)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt before building",
)
def build(
    input_files,
    workdir,
    rootpath,
    select_ids,
    threads,
    verbose,
    force,
):
    """Build an index from a list of definition.

    Examples:
    """

    ids = []
    for item in select_ids:
        ids.extend(item.split(","))
    ids = [id.strip() for id in ids]

    idt = IndexDefinitionTools()

    for input_file in input_files:
        click.echo(input_file)

        table = idt.load_db(input_file)

        for i in table.values():
            click.echo(f"Build {i.id}...")

            # Show confirmation with size estimation (skip if -f/--force is used)
            if not force:
                click.echo()
                try:
                    click.echo(f"  Estimated index size: {str(i.get_stored_size())}")
                    click.echo()

                    if not click.confirm("Proceed with build?", default=True):
                        click.echo("Build cancelled")
                        return
                except Exception as e:
                    click.echo(f"Warning: Could not estimate build size: {e}", err=True)
                    if not click.confirm("Proceed with build anyway?", default=True):
                        click.echo("Build cancelled")
                        return
                click.echo()

            try:
                builder = IndexBuilder(
                    output_index_path=workdir,
                    k=i.kmer_size,
                )

                fof = FofManager()
                assert builder, "Could not initialize builder"

                for s in i.samples.values():
                    sample_files = [rootpath + f for f in s.files] if rootpath else s.files
                    fof.add_sample(sample_files, s.id or "")

                builder.create_subindex(
                    name=i.id,
                    samples=fof,
                    assembled=True,
                    bloom_size=i.bf_size,
                    n_partitions=i.partition_count,
                    n_threads=threads,
                    auto_check=True,
                )

            except Exception as e:
                if verbose:
                    click.echo(
                        click.style(
                            traceback.format_exc(), fg="red", bold=True, dim=True
                        ),
                        err=True,
                        color=True,
                    )
                click.echo(
                    click.style(f"Error: {e}", fg="red", bold=True),
                    err=True,
                    color=True,
                )
