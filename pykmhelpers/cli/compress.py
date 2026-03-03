import click
from pykmhelpers import KmindexWrapper, KmindexRegistry

@click.command(name="compress")
@click.option(
    "--registry-path",
    "-r",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to kmindex registry",
)
@click.option(
    "--index-name",
    "-n",
    required=True,
    help="Name of the index to compress",
)
@click.option(
    "--block-size",
    type=int,
    default=8,
    help="Size of uncompressed blocks in MB (default: 8)",
)
@click.option(
    "--sampling",
    "-s",
    type=int,
    default=20000,
    help="Number of rows to sample for reordering (default: 20000)",
)
@click.option(
    "--column-per-block",
    type=int,
    default=0,
    help="Reorder columns by group of N (0=all columns, must be multiple of 8) (default: 0)",
)
@click.option(
    "--cpr-level",
    type=int,
    default=3,
    help="Compression level [1-22] (default: 3)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=14,
    help="Number of threads (default: 14)",
)
@click.option(
    "--reorder",
    is_flag=True,
    default=False,
    help="Enable column reordering before compression",
)
@click.option(
    "--delete",
    is_flag=True,
    default=False,
    help="Delete uncompressed index after successful compression",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Check query results after compressing",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def kmindex_compress(
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
    verbose,
):
    """Compress an index.

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
    try:
        registry = KmindexRegistry(registry_path)

        if verbose:
            click.echo(f"Preparing to compress index: {index_name}")
            click.echo(f"  Registry: {registry_path}")

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
            verbose="debug" if verbose else "info",
        )

        click.echo(f"✓ Compression completed successfully")
        click.echo(f"  Index: {index_name}")
        click.echo(f"  Block size: {block_size} MB")
        click.echo(f"  Compression level: {cpr_level}")

        if reorder:
            click.echo(f"  Column reordering: enabled")

        if delete:
            click.echo(f"  Uncompressed index deleted")

    except ValueError as e:
        raise click.ClickException(f"Registry error: {e}")
    except FileNotFoundError as e:
        raise click.ClickException(f"Registry file not found: {e}")
    except Exception as e:
        raise click.ClickException(f"Compression failed: {e}")
