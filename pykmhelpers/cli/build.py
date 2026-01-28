"""Build k-mer index command."""

import click
import os
import traceback
from pykmhelpers.operations.fof import FofManager
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

        for i in table.indices.values():
            click.echo(f"Build {i.id}...")

            try:

                builder = IndexBuilder(
                    output_index_path=workdir, k=i.kmer_size, z=i.findere_z
                )

                fof = FofManager()

                for s in i.samples.values():
                    assert s.id
                    fof.add_sample(s.files[0], s.id)

                builder.create_subindex(
                    name=i.id,
                    samples=fof,
                    assembled=True,
                    bloom_size=i.bf_size,
                    n_partitions=i.partition_count,
                    n_threads=threads,
                    auto_check=True,
                )

                assert builder, "Could not initialize builder"

            except Exception as e:
                traceback.print_exc()
                click.echo(f"Error: {e}")
