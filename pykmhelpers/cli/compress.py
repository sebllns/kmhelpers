import logging

import click

from pykmhelpers import KmindexRegistry
from pykmhelpers.cli.shared import confirm, select_shards
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
    "--sh",
    "--shard",
    "index_ids",
    multiple=True,
    required=False,
    help="🏷️   Shards to compress, as names or glob patterns (repeatable or "
    "comma-separated: --shard idx_g0_p1, --shard 'idx_g0_*'; default: all).",
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
    index_ids,
    block_size,
    sampling,
    column_per_block,
    cpr_level,
    threads,
    reorder,
    delete,
    check,
):
    """Compress shards of a registry.

    \b
    Input:  kmindex registry (-r), shards (--shard, default: all)
    Output: compressed shards in place within the registry

    Shards are compressed one after the other. A failed shard does not stop
    the others; the command fails at the end if any did.

    Examples:

      \b
      # Compress every shard of the registry
      kmhelpers compress -r ./registry

      \b
      # Compress the shards of one group, with column reordering
      kmhelpers compress -r ./registry --shard 'my_index_g0_*' --reorder -s 50000

      \b
      # Custom compression level with multiple threads
      kmhelpers compress -r ./registry --shard my_index_g0_p1 --cpr-level 6 -t 16
    """
    registry = KmindexRegistry(registry_path)
    index_ids = select_shards(registry, index_ids)
    if not index_ids:
        raise click.UsageError(f"No shard in registry {registry_path}")

    if delete and not confirm(
        ctx,
        f"Delete the uncompressed matrices of {len(index_ids)} shard(s) "
        f"({', '.join(index_ids)}) after compression?",
    ):
        raise click.Abort()

    logger.info(f"Compressing {len(index_ids)} shard(s) of {registry_path}")
    logger.info(f"  Compression level: {cpr_level}")
    if reorder:
        logger.info(f"  Column reordering: enabled")

    failed = []
    for index_name in index_ids:
        try:
            logger.info(f"Compressing shard: {index_name}")
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
            logger.info(f"✓ Compressed {index_name}")
        except Exception as e:
            Log.handle_exception(logger, e, f"Compression of {index_name} failed")
            failed.append(index_name)

    if failed:
        raise click.ClickException(
            f"FAILED ('compress'): {len(failed)} of {len(index_ids)} shard(s): "
            f"{', '.join(failed)}"
        )
    logger.info(f"SUCCESS ('compress'): {len(index_ids)} shard(s)")
