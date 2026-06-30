import logging

import click

from pykmhelpers import KmindexRegistry, KmindexWrapper
from pykmhelpers.core.log import Log

logger = logging.getLogger(__name__)


@click.command(name="compress")
@click.pass_context
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="📁  Path to kmindex registry.",
)
@click.option(
    "--index-name",
    "-n",
    required=True,
    help="🏷️   Name of the index to compress.",
)
@click.option(
    "--block-size",
    type=int,
    default=8,
    show_default=True,
    help="⚙   Size of uncompressed blocks in MB.",
)
@click.option(
    "--sampling",
    "-s",
    type=int,
    default=20000,
    show_default=True,
    help="⚙   Number of rows to sample for reordering.",
)
@click.option(
    "--column-per-block",
    type=int,
    default=0,
    show_default=True,
    help="⚙   Reorder columns by group of N (0=all columns, must be multiple of 8).",
)
@click.option(
    "--cpr-level",
    type=int,
    default=3,
    show_default=True,
    help="⚙   Compression level [1-22].",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=14,
    show_default=True,
    help="⚙️  Number of threads.",
)
@click.option(
    "--reorder",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Enable column reordering before compression.",
)
@click.option(
    "--delete",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Delete uncompressed index after successful compression.",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Check query results after compressing.",
)
def kmindex_compress(
    ctx,
    registry_path,
    index_name,
    block_size,
    sampling,
    column_per_block,
    cpr_level,
    threads,
    reorder,
    delete,
    check,
):
    """Compress an index.

    \b
    Input:  kmindex registry (-r), index name (-n)
    Output: compressed index in place within the registry

    Registry-based compression using the KmindexWrapper. Simpler interface
    for compressing indices managed in a registry.

    Examples:
      # Basic compression
      kmhelpers kmindex-compress -r ./registry -n my_index

      # Compression with column reordering
      kmhelpers kmindex-compress -r ./registry -n my_index --reorder -s 50000

      # Custom compression level with multiple threads
      kmhelpers kmindex-compress -r ./registry -n my_index --cpr-level 6 -t 16
    """
    if delete and not (ctx.obj or {}).get("yes", False):
        if not click.confirm(
            f"Delete uncompressed index '{index_name}' after compression?",
            default=False,
        ):
            raise click.Abort()

    try:
        registry = KmindexRegistry(registry_path)

        logger.info(f"Preparing to compress index: {index_name}")
        logger.info(f"  Registry: {registry_path}")
        logger.info(f"  Compression level: {cpr_level}")

        if reorder:
            logger.info(f"  Column reordering: enabled")

        registry.compress(
            index_name=index_name,
            block_size=block_size,
            sampling=sampling,
            column_per_block=column_per_block,
            cpr_level=cpr_level,
            threads=threads,
            reorder=reorder,
            delete_uncompressed=delete,
            check_results=check,
            verbose="debug" if logger.isEnabledFor(logging.DEBUG) else "info",
        )

        logger.info(f"✓ Compression completed successfully")
        logger.info(f"  Index: {index_name}")
        logger.info(f"  Block size: {block_size} MB")
        if reorder:
            logger.info(f"  Column reordered")
        if delete:
            logger.info(f"  Uncompressed index deleted")

    except Exception as e:
        Log.handle_exception(logger, e, "Compression failed")
