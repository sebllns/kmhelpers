"""Build k-mer index command."""

import click

from pykmhelpers import KmindexRegistry, KmindexWrapper
from pykmhelpers.cli.shared import estimate_build_size


@click.group()
def kmindex():
    """Wrapper commands for low-level interaction with kmindex."""
    pass


@kmindex.command("build")
@click.option(
    "--fof",
    required=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="File-of-Files (FOF) listing input samples",
)
@click.option(
    "--output-registry",
    "-r",
    required=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Output kmindex registry path (created if doesn't exist)",
)
@click.option(
    "--output-index-dir",
    default=".subindexes",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Directory for index data (default: .subindexes)",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    help="K-mer size (default: 25)",
)
@click.option(
    "--minim-size",
    "-m",
    type=int,
    default=10,
    help="Minimizer size (default: 10)",
)
@click.option(
    "--bloom-size",
    type=int,
    help="Bloom filter size for presence/absence (mutually exclusive with --nb-cell)",
)
@click.option(
    "--nb-cell",
    type=int,
    help="Number of cells for abundance counting (mutually exclusive with --bloom-size)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="Number of threads (default: 1)",
)
@click.option(
    "--register-as",
    "-n",
    help="Register index with this ID (auto-generated if not provided)",
)
@click.option(
    "--compress-intermediate",
    is_flag=True,
    help="Compress intermediate files during build",
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
    fof,
    output_registry,
    output_index_dir,
    kmer_size,
    minim_size,
    bloom_size,
    nb_cell,
    threads,
    register_as,
    compress_intermediate,
    verbose,
    force,
):
    """Build k-mer index from FOF file.

    Examples:
      # Build presence/absence index
      kmhelpers build --fof samples.fof -r ./registry --bloom-size 10000000

      # Build abundance index with custom k-mer size
      kmhelpers build --fof samples.fof -r ./registry --nb-cell 65536 -k 31

      # Build with multiple threads and register
      kmhelpers build --fof samples.fof -r ./registry --bloom-size 10000000 -t 8 -n my_index
    """

    # Validate parameters
    if bloom_size is None and nb_cell is None:
        raise click.BadParameter("Must specify either --bloom-size or --nb-cell")

    if bloom_size is not None and nb_cell is not None:
        raise click.BadParameter("Cannot specify both --bloom-size and --nb-cell")

    if minim_size >= kmer_size:
        raise click.BadParameter(
            f"minim-size ({minim_size}) must be less than kmer-size ({kmer_size})"
        )

    try:
        click.echo("Initializing build...")
        wrapper = KmindexWrapper()

        click.echo(f"Building index from FOF: {fof}")
        click.echo(f"  K-mer size: {kmer_size}")
        click.echo(f"  Minimizer size: {minim_size}")

        if bloom_size is not None:
            click.echo(f"  Bloom size: {bloom_size}")
        if nb_cell is not None:
            click.echo(f"  Abundance cells: {nb_cell}")

        click.echo(f"  Threads: {threads}")

        # Show confirmation with size estimation (skip if -f/--force is used)
        if not force:
            click.echo()
            try:
                size_est = estimate_build_size(
                    fof, bloom_size=bloom_size, nb_cell=nb_cell
                )
                click.echo("Build Size Estimate:")
                # click.echo(
                #     f"  Input data: {size_est['input_size_str']} ({size_est['sample_count']} samples)"
                # )
                click.echo(f"  Estimated index size: {size_est['index_size_min_str']}")
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

        # Build index using wrapper
        index_path, registry_path = wrapper.build(
            input_fof_file=fof,
            output_registry_path=output_registry,
            output_index_dir=output_index_dir,
            k=kmer_size,
            minim_size=minim_size,
            bloom_size=bloom_size,
            nb_cell=nb_cell,
            threads=threads,
            compress_intermediate=compress_intermediate,
            register_as=register_as,
        )

        click.echo(f"✓ Build completed successfully")
        click.echo(f"  Index directory: {index_path}")
        click.echo(f"  Registry: {registry_path}")

        # Show registered index info
        if register_as:
            registry = KmindexRegistry(output_registry)
            if registry.has_index(register_as):
                index = registry.get_index(register_as)
                click.echo(f"  Registered as: {register_as}")
                click.echo(f"    Samples: {index.nb_samples}")
                click.echo(f"    Partitions: {index.nb_partitions}")

    except Exception as e:
        raise click.ClickException(f"Build failed: {e}")
