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


@click.command(name="build-subindex")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--workdir",
    "-w",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory path (created if doesn't exist)",
)
@click.option(
    "--rootpath",
    "-r",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to resolve relative sample paths. By default, relative \
paths are resolved from the run directory; use this option if you \
need to resolve them from a different location.",
)
@click.option(
    "--from",
    "reuse_from",
    required=False,
    help="⚙   Parent index ID to reuse parameters from. Takes precedence over parent_index that can be specified in definition file.",
)
@click.option(
    "--index-ids",
    "-n",
    multiple=True,
    required=False,
    help="⚙   Index IDs to build. Can be specified multiple times (-n id1 -n id2) or comma-separated (-n id1,id2).",
)
@click.option(
    "--minim-size",
    type=int,
    default=10,
    help="⚙   Minimizer size (4-15, default: 10).",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="⚙   Number of threads (default: 1).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="🚩  Verbose output.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="🚩  Skip confirmation prompt before building.",
)
@click.option(
    "--skip-compression",
    is_flag=True,
    help="🚩  Skip compression of intermediate files during index building. Can improve performance on fast drives where I/O is not a bottleneck.",
)
def build_subindex(
    input_files,
    workdir,
    rootpath,
    reuse_from,
    index_ids,
    minim_size,
    threads,
    verbose,
    force,
    skip_compression,
):
    """Build and register individual subindices from definition files.

    📄 INPUT_FILES are one or more serialized index definition files (.json/.yaml).
    Only the indices matching the given --index-ids will be built. If not specified, all indices are built.

    Examples:

    \b
    # Build a single subindex
    kmhelpers build-subindex db.yaml -w /output -n my_index

    \b
    # Build multiple subindices (comma-separated or repeated flags)
    kmhelpers build-subindex db.yaml -w /output -n idx1,idx2
    kmhelpers build-subindex db.yaml -w /output -n idx1 -n idx2

    \b
    # Build reusing parameters from an existing index, skipping confirmation
    kmhelpers build-subindex db.yaml -w /output -n my_index --from parent_index -f
    """

    # Bump logging level to INFO if -v is set and current level is higher
    if verbose:
        force_verbose_mode()

    idt = IndexDefinitionTools()

    ids = [id for entry in index_ids for id in entry.split(",") if id]

    for input_file in input_files:
        logger.debug(f"Load db: {input_file}")

        db = idt.deserialize(input_file)

        for table in db:
            for i in table.index_table.values():
                if ids and i.name not in ids:
                    continue

                assert i.name, "Index name empty or null"
                logger.info(f"Build {i.name}...")

                try:
                    builder = IndexBuilder(
                        workdir=workdir,
                        k=i.kmer_size,
                    )

                    fof = FofManager()
                    assert builder, "Could not initialize builder"

                    if builder.has_subindex(i.name):
                        logger.warning(
                            f"Index {i.name} already found in registry... Skipping"
                        )
                        continue

                    # Show confirmation with size estimation (skip if -f/--force is used)
                    if not force:
                        try:
                            logger.info(
                                f"  Estimated index size: {str(i.get_stored_size())}"
                            )

                            if not click.confirm("Proceed with build?", default=True):
                                logger.info("Build cancelled")
                                continue
                        except Exception as e:
                            logger.warning(f"Could not estimate build size: {e}")
                            if not click.confirm(
                                "Proceed with build anyway?", default=True
                            ):
                                logger.info("Build cancelled")
                                continue

                    parent_index = i.get_parent()

                    if reuse_from:
                        parent_index = reuse_from

                    if parent_index:
                        assert builder.has_subindex(
                            parent_index
                        ), f"Could not find parent index: {parent_index}"

                    for s in i.samples.values():
                        if s.name:
                            try:
                                sample_files = (
                                    [rootpath + f for f in s.files]
                                    if rootpath
                                    else s.files
                                )
                                fof.add_sample(sample_files, s.name)
                            except Exception as e:
                                logger.warning(f"Error adding sample to FOF: {e}")

                    builder.create_subindex(
                        name=i.name,
                        samples=fof,
                        abundance_min=i.abundance_min,
                        bloom_size=i.bf_size,
                        n_partitions=i.partition_count,
                        n_threads=threads,
                        auto_check=True,
                        build_from=parent_index,
                        compress_intermediate=not skip_compression,
                        minim_size=minim_size,
                    )

                except Exception as e:
                    if verbose:
                        logger.exception(
                            f"Build failed for {i.name}: {e} ({type(e).__name__})"
                        )
                    else:
                        logger.error(
                            f"Build failed for {i.name}: {e} ({type(e).__name__})"
                        )
