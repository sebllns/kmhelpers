"""Build k-mer index command."""

import logging
import os

import click

from pykmhelpers.cli.shared import force_verbose_mode
from pykmhelpers.core.constants import KMHELPERS_VERSION
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import DbFields, IndexDefinitionTools

logger = logging.getLogger(__name__)


def _parse_spans(spans):
    """Parse span arguments supporting multiple formats:
    - Single values: --span 28
    - Comma-separated: --span 27,28,29
    - Range notation: --span [27-30] or --span 27-30
    """
    result = []
    for item in spans:
        item = item.strip()
        # Handle range notation [27-30] or 27-30
        if "[" in item and "-" in item:
            item = item.strip("[]")

        if "-" in item and not item.startswith("-"):
            # Range notation: 27-30
            try:
                start, end = item.split("-")
                result.extend(
                    str(i) for i in range(int(start.strip()), int(end.strip()) + 1)
                )
            except ValueError:
                result.append(item)
        else:
            # Comma-separated or single value
            result.extend(s.strip() for s in item.split(","))

    return result


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
    "--from", "reuse_from", required=False, help="Reuse parameters from given index ID"
)
@click.option(
    "--span",
    "-s",
    multiple=True,
    help="Build only selected span (e.g., --span 28, --span 27,28,29, --span 27-30, --span [27-30])",
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
    reuse_from,
    span,
    threads,
    verbose,
    force,
):
    """Build an index from a list of definition.

    Examples:
    """

    # Bump logging level to INFO if -v is set and current level is higher
    if verbose:
        force_verbose_mode()

    selected_spans = _parse_spans(span)

    idt = IndexDefinitionTools()

    for input_file in input_files:
        logger.info(f"Load db: {input_file}")

        table = idt.load_db(input_file)

        for i in table.index_table.values():
            assert i.name, "Index name empty or null"
            logger.info(f"Build {i.name}...")

            # Show confirmation with size estimation (skip if -f/--force is used)
            if not force:
                try:
                    logger.info(f"  Estimated index size: {str(i.get_stored_size())}")

                    if not click.confirm("Proceed with build?", default=True):
                        logger.info("Build cancelled")
                        return
                except Exception as e:
                    logger.warning(f"Could not estimate build size: {e}")
                    if not click.confirm("Proceed with build anyway?", default=True):
                        logger.info("Build cancelled")
                        return

            try:
                builder = IndexBuilder(
                    output_index_path=workdir,
                    k=i.kmer_size,
                )

                fof = FofManager()
                assert builder, "Could not initialize builder"

                for s in i.samples.values():
                    assert s.name, "Sample name empty or null"
                    sample_files = (
                        [rootpath + f for f in s.files] if rootpath else s.files
                    )
                    fof.add_sample(sample_files, s.name)

                parent_index = i.get_link(DbFields.PARENT_INDEX.value)

                if reuse_from:
                    parent_index = reuse_from

                builder.create_subindex(
                    name=i.name,
                    samples=fof,
                    assembled=True,
                    bloom_size=i.bf_size,
                    n_partitions=i.partition_count,
                    n_threads=threads,
                    auto_check=True,
                    build_from=parent_index,
                )

            except Exception as e:
                if verbose:
                    logger.exception(f"Build failed for {i.name}")
                else:
                    logger.error(f"Error: {e}")
