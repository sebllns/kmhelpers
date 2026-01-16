"""Project workflow commands for building and querying indices."""

import os
import click
from pathlib import Path
from datetime import datetime
from pykmhelpers import KmindexRegistry
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.operations.fof import FofManager
from pykmhelpers.operations.query import KmindexQuery
from pykmhelpers.cli.project_shell import ProjectShell
from pykmhelpers.cli.shared import (
    estimate_build_size,
    get_project_config,
    save_project_config,
)


@click.group()
def project():
    """[EXPERIMENTAL] Opinionated project workflow for building and querying indices."""
    click.echo("⚠ Warning: The 'project' command is experimental, may not work correctly and may change in future versions.", err=True)
    pass


@project.command(name="create")
@click.argument("project_path", type=click.Path())
@click.option(
    "--k",
    "--kmer-size",
    "kmer_size",
    type=int,
    default=31,
    help="K-mer size (default: 31)",
)
@click.option(
    "--z",
    type=int,
    default=6,
    help="Z offset for findere algorithm (s = k - z). Constraint: 0 < k - z <= 36 (default: 6)",
)
@click.option(
    "--desc",
    "description",
    help="Optional project description",
)
@click.option(
    "--open",
    "open_shell",
    is_flag=True,
    help="Open the project shell immediately after creation",
)
def project_create(project_path, kmer_size, z, description, open_shell):
    """Initialize a new kmhelpers project.

    The findere algorithm uses k-mers reduced to s-mers through the z offset:
    - K: full k-mer size
    - z: offset used to reduce k-mers during indexing to reduce false positives
    - s: actual s-mer size used in index (s = k - z)

    Important constraints:
    - 0 < K - z <= 36 to avoid hash collisions in Bloom filters and ensure valid smers.

    Valid examples: (k=31, z=6) → s=25 ✓, (k=37, z=1) → s=36 ✓
    Invalid examples: (k=37, z=0) → s=37 ✗, (k=31, z=31) → s=0 ✗
    """

    try:
        # Create base directory
        os.makedirs(project_path, exist_ok=True)

        # Validate basic parameter ranges
        if kmer_size <= 0:
            raise click.BadParameter(f"K-mer size (k) must be > 0, got {kmer_size}")

        if z < 0:
            raise click.BadParameter(f"Z offset must be >= 0, got {z}")

        # Calculate smer size from k and z
        smer_size = kmer_size - z

        # Validate constraint: 0 < k - z <= 36
        if smer_size <= 0:
            raise click.BadParameter(
                f"Constraint violation: k - z must be > 0, but got {kmer_size} - {z} = {smer_size}. "
                f"Ensure z is less than k."
            )

        if smer_size > 36:
            raise click.BadParameter(
                f"Constraint violation: k - z must be <= 36, but got {kmer_size} - {z} = {smer_size}. "
            )

        # Create IndexBuilder to set up directory structure
        IndexBuilder(project_path, k=kmer_size, z=z)

        # Create and save project metadata
        config = {
            "version": "1.0",
            "k": kmer_size,
            "z": z,
            "s": smer_size,
            "path": str(Path(project_path).absolute()),
            "date_creation": datetime.now().isoformat(),
        }

        # Add optional description if provided
        if description:
            config["description"] = description

        save_project_config(project_path, config)

        click.echo(f"✓ Project created: {project_path}")
        click.echo(f"  K-mer size (k): {kmer_size}")
        click.echo(f"  Z offset: {z}")
        click.echo(f"  Smer size (s = k - z): {smer_size}")
        click.echo(f"  Created: {config['date_creation']}")
        if description:
            click.echo(f"  Description: {description}")
        click.echo(f"  Structure:")
        click.echo(f"    - registry/")
        click.echo(f"    - .subindexes/")
        click.echo(f"    - logs/")

        # Launch interactive shell if requested
        if open_shell:
            click.echo()
            shell = ProjectShell(project_path, config)
            shell.run()

    except click.BadParameter:
        raise
    except Exception as e:
        raise click.ClickException(f"Failed to create project: {e}")


@project.command(name="open")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def project_open(project_path):
    """Open an existing kmhelpers project in interactive shell mode.

    Launches an interactive REPL where you can execute project-scoped commands
    like 'build', 'query', 'info', etc. without repeating the project path.

    Examples of commands in the shell:
      kmhelpers(my_project)> info
      kmhelpers(my_project)> build my_index --fof samples.fof --bloom-size 10000000
      kmhelpers(my_project)> query my_index --query query.fa --output results
      kmhelpers(my_project)> list
      kmhelpers(my_project)> exit
    """
    try:
        # Load project configuration
        config = get_project_config(project_path)

        # Launch interactive shell
        shell = ProjectShell(project_path, config)
        shell.run()

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Failed to open project: {e}")


@project.command(name="build")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("index_name")
@click.option(
    "--fof",
    required=True,
    type=click.Path(exists=True, file_okay=True),
    help="Path to FOF file",
)
@click.option(
    "--bloom-size",
    type=int,
    required=True,
    help="Bloom filter size (bits)",
)
@click.option(
    "--assembled",
    is_flag=True,
    default=False,
    help="Mark index as assembled data",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=0,
    help="Number of threads (0 = auto-detect)",
)
@click.option(
    "--partitions",
    type=int,
    default=256,
    help="Number of partitions (default: 256)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt before building",
)
def project_build(
    project_path,
    index_name,
    fof,
    bloom_size,
    assembled,
    threads,
    partitions,
    verbose,
    force,
):
    """Build an index within the project."""

    try:
        # Load project configuration
        config = get_project_config(project_path)

        # Load FOF file into FofManager
        manager = FofManager()
        try:
            with open(fof, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 2:
                            sample_name, file_path = parts[0], parts[1]
                            manager.add_sample(file_path, sample_name)
        except Exception as e:
            raise click.ClickException(f"Failed to load FOF file: {e}")

        if verbose:
            click.echo(f"Building index '{index_name}' in project: {project_path}")
            click.echo(f"  Samples: {manager.get_sample_count()}")
            click.echo(f"  K-mer size: {config['k']}")

        # Show confirmation with size estimation (skip if -f/--force is used)
        if not force:
            click.echo()
            try:
                size_est = estimate_build_size(fof, bloom_size=bloom_size, nb_cell=None)
                click.echo("Build Size Estimate:")
                click.echo(
                    f"  Input data: {size_est['input_size_str']} ({size_est['sample_count']} samples)"
                )
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

        # Create IndexBuilder
        builder = IndexBuilder(project_path, k=config["k"], z=config["z"])

        # Build the subindex
        index = builder.create_subindex(
            name=index_name,
            samples=manager,
            assembled=assembled,
            bloom_size=bloom_size,
            n_partitions=partitions,
            n_threads=threads,
            auto_check=True,
        )

        click.echo(f"✓ Index built successfully")
        click.echo(f"  Index name: {index_name}")
        click.echo(f"  Samples: {index.nb_samples}")
        click.echo(f"  Partitions: {index.nb_partitions}")
        click.echo(f"  K-mer size: {index.kmer_size}")

    except Exception as e:
        raise click.ClickException(f"Failed to build index: {e}")


@project.command(name="query")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("index_name")
@click.option(
    "--query",
    "-q",
    required=True,
    type=click.Path(exists=True, file_okay=True),
    help="Path to query file (FASTA/FASTQ)",
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    default="query_results",
    type=click.Path(file_okay=False),
    help="Output directory (default: query_results)",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    default=1,
    help="Number of threads",
)
@click.option(
    "--single-query",
    type=str,
    help="Single query mode (batch name)",
)
@click.option(
    "--aggregate",
    is_flag=True,
    default=False,
    help="Aggregate results across indices",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
def project_query(
    project_path,
    index_name,
    query,
    output_dir,
    threads,
    single_query,
    aggregate,
    verbose,
):
    """Query an index within the project."""

    try:
        # Load project configuration
        config = get_project_config(project_path)

        # Resolve registry path
        registry_path = os.path.join(project_path, "registry")
        if not os.path.exists(registry_path):
            raise click.ClickException(
                f"Registry not found in project: {registry_path}"
            )

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        if verbose:
            click.echo(f"Querying index '{index_name}' from project: {project_path}")
            click.echo(f"  Registry: {registry_path}")
            click.echo(f"  Query file: {query}")

        # Initialize KmindexQuery
        kquery = KmindexQuery(query)

        # Execute query
        results = kquery.execute(
            registry_path=registry_path,
            output_dir=output_dir,
            index_ids=[index_name],
            z=config["z"],
            single_query=single_query,
            aggregate=aggregate,
            threads=threads,
        )

        click.echo(f"✓ Query completed")
        click.echo(f"  Index: {index_name}")
        click.echo(f"  Results: {output_dir}")
        click.echo(f"  Query results found: {len(results)}")

        if verbose and results:
            for result in results:
                click.echo(f"    - {result}")

    except Exception as e:
        raise click.ClickException(f"Query failed: {e}")


@project.command(name="info")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False))
def project_info(project_path):
    """Show project information and indices."""

    try:
        # Load project configuration
        config = get_project_config(project_path)

        click.echo(f"Project: {project_path}")
        click.echo(f"  Version: {config.get('version', 'unknown')}")
        click.echo(f"  K-mer size (k): {config['k']}")
        click.echo(f"  Minimizer size (z): {config['z']}")
        click.echo(f"  Span (s): {config['s']}")
        click.echo(f"  Path: {config.get('path', 'unknown')}")
        click.echo(f"  Created: {config.get('date_creation', 'unknown')}")
        if config.get('description'):
            click.echo(f"  Description: {config['description']}")
        click.echo()

        # Show directory structure
        click.echo("Project structure:")
        for subdir in ["registry", ".subindexes", "logs"]:
            dir_path = os.path.join(project_path, subdir)
            exists = "✓" if os.path.exists(dir_path) else "✗"
            click.echo(f"  {exists} {subdir}/")

        click.echo()

        # List indices in registry
        registry_path = os.path.join(project_path, "registry")
        if os.path.exists(registry_path):
            try:
                registry = KmindexRegistry(registry_path)
                indices = registry.list_indices()

                if indices:
                    click.echo(f"Registered indices ({len(indices)}):")
                    for idx_name in indices:
                        index = registry.get_index(idx_name)
                        click.echo(f"  {idx_name}")
                        click.echo(f"    - Samples: {index.nb_samples}")
                        click.echo(f"    - Partitions: {index.nb_partitions}")
                        click.echo(f"    - K-mer size: {index.kmer_size}")
                else:
                    click.echo("No indices registered yet")
            except Exception as e:
                click.echo(f"Error reading registry: {e}", err=True)
        else:
            click.echo("Registry not yet created")

    except Exception as e:
        raise click.ClickException(f"Failed to get project info: {e}")
