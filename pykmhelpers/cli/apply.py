"""Build k-mer index command."""

import datetime
import logging
import os

import click

import pykmhelpers.cli.shared as shared
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.core.constants import KMHELPERS_VERSION
from pykmhelpers.core.log import Log
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.fof import FofManager

logger = logging.getLogger(__name__)


def _parse_spans(spans):
    """Parse span arguments supporting multiple formats:
    - Single values: --span 28
    - Comma-separated: --span 27,28,29
    - Range notation: --span [27-30] or --span 27-30
    """
    result = []
    for item in spans:
        # Handle range notation [27-30] or 27-30
        item = item.strip(" []-")
        if "-" in item:
            # Range notation: 27-30
            try:
                start, end = item.split("-")
                result.extend(
                    i for i in range(int(start.strip()), int(end.strip()) + 1)
                )
            except ValueError:
                result.append(item)
        else:
            # Comma-separated or single value
            result.extend(int(s.strip()) for s in item.split(","))
    return result


@click.command(name="apply")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--config",
    "-c",
    envvar="KMHELPERS_CONFIG",
    required=False,
    type=click.Path(file_okay=True, dir_okay=False, exists=True),
    help="📄  Input configuration file (command line arguments take precedence when both are provided).",
)
@click.option(
    "--workdir",
    "-w",
    envvar="KMHELPERS_WORKDIR",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Output directory path (created if doesn't exist).",
)
@click.option(
    "--basepath",
    "-b",
    envvar="KMHELPERS_SAMPLE_ROOT",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to resolve relative sample paths. By default, relative \
paths are resolved from the run directory; use this option if you \
need to resolve them from a different location.",
)
@click.option(
    "--registry",
    "-r",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to kmindex registry, absolute or relative from workdir (created if doesn't exist).",
)
@click.option(
    "--output-dir",
    "-o",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to kmindex output directory, absolute or relative from workdir (created if doesn't exist).",
)
@click.option(
    "--span",
    "-s",
    multiple=True,
    required=False,
    help="⚙   Build only selected span (e.g., --span 28, --span 27,28,29, --span 27-30, --span [27-30]).",
)
@click.option(
    "--name",
    "-n",
    "index_ids",
    multiple=True,
    required=False,
    help="⚙   Index IDs to build. Can be specified multiple times (-n id1 -n id2) or comma-separated (-n id1,id2).",
)
@click.option(
    "--from",
    "reuse_from",
    required=False,
    help="⚙   Parent index ID to reuse parameters from. Takes precedence over parent_index that can be specified in definition file.",
)
@click.option(
    "--minim-size",
    type=int,
    required=False,
    help="⚙   Minimizer size (4-15, default: 10).",
)
@click.option(
    "--threads",
    "-t",
    envvar="KMHELPERS_THREADS",
    type=int,
    required=False,
    help="⚙   Number of threads (default: 1).",
)
@click.option(
    "--verbose",
    "-v",
    envvar="KMHELPERS_VERBOSE",
    is_flag=True,
    help="🚩  Verbose output.",
)
@click.option(
    "--force",
    "-f",
    envvar="KMHELPERS_SKIP_CONFIRMATION",
    is_flag=True,
    help="🚩  Skip confirmation prompt before building. NOTE: disabled for now",
)
@click.option(
    "--skip-compression",
    envvar="KMHELPERS_SKIP_COMPRESSION",
    is_flag=True,
    help="🚩  Skip compression of intermediate files during index building. Can improve performance on fast drives where I/O is not a bottleneck.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="🚩  Output a bash script with build commands without executing them.",
)
@click.option(
    "--plan",
    is_flag=True,
    help="🚩  Like dry-run, but with paths checking (e.g. samples with missing files won't be exported in FOF file) \n NOTE: this option will become a command itself in a future release.",
)
@click.option(
    "--merge-spans",
    "-m",
    required=False,
    type=click.Path(file_okay=True, dir_okay=False, exists=True),
    help="📄  TODO: Input file, defining span merges. Currently does nothing, will be added in a future release.",
)
def apply(
    input_files,
    config,
    workdir,
    basepath,
    registry,
    output_dir,
    span,
    index_ids,
    reuse_from,
    minim_size,
    threads,
    verbose,
    force,
    skip_compression,
    dry_run,
    plan,
    merge_spans,
):
    """Apply changes and build indices from definition files.

    📄 INPUT_FILES are one or more index definition files (.json/.yaml). For each file,
    the declared indices are built and registered. If the file type is an index definition,
    indices are built directly; if it is a span registry, sub-index definition files are
    resolved from the same directory and merged into the named indices after building.
    Parent indices are built automatically when required. Only indices matching --name or
    --span are processed; if neither is specified, all declared indices are built.

    Examples:

    \b
    # Build all indices declared in a definition file
    kmhelpers apply index.yaml -w /output

    \b
    # Build only selected indices by name (comma-separated or repeated flags)
    kmhelpers apply index.yaml -w /output -n idx1,idx2
    kmhelpers apply index.yaml -w /output -n idx1 -n idx2

    \b
    # Build only selected k-mer spans from a span registry
    kmhelpers apply registry.yaml -w /output -s 28
    kmhelpers apply registry.yaml -w /output -s 27,28,29

    \b
    # Dry run: print build commands without executing
    kmhelpers apply index.yaml -w /output --dry-run

    \b
    # Reuse parameters from an existing parent index
    kmhelpers apply index.yaml -w /output -n my_index --from parent_index
    """

    abort_msg = "Command 'apply' aborted."

    # Bump logging level to INFO if -v is set and current level is higher
    if verbose:
        shared.force_verbose_mode()

    config_map = {}
    if config:
        try:
            config_map = shared.deserialize(config)
        except Exception as e:
            Log.handle_exception(
                logger, e, f"Could not deserialize config from {config}"
            )
            raise click.ClickException(abort_msg)

    try:
        selected_ids = [id for entry in index_ids for id in entry.split(",") if id]
        selected_spans = _parse_spans(span)

        if not workdir:
            workdir = config_map.get("workdir")
        assert workdir, "Required parameter 'workdir' was not provided."

        if not registry:
            registry = config_map.get("registry", "")

        if not basepath:
            basepath = config_map.get("rootpath", "")

        if basepath and not os.path.isdir(basepath):
            logger.warning(f"Data root directory not found at {basepath}")

        if not output_dir:
            output_dir = config_map.get("output_dir", "kmindex_data")

        if not threads:
            threads = config_map.get("threads", 1)

        if not minim_size:
            minim_size = config_map.get("minim_size", 10)

    except Exception as e:
        Log.handle_exception(logger, e, f"Invalid argument.")
        raise click.ClickException(abort_msg)

    iops = ops.IndexOps(
        config=ops.IndexOpsConfig(
            workdir=workdir,
            index_data_folder=output_dir,
            registry_name=registry,
            minimizer_length=int(minim_size),
            sample_rootpath=basepath,
            kmindex_threads=threads,
            kmindex_skip_compression=skip_compression,
            kmindex_build_from=reuse_from,
            filter_names=selected_ids,
            filter_spans=selected_spans,
            log_folder="logs",
            plan=plan,
            dry_run=dry_run,
        )
    )

    for input_file in input_files:
        try:
            logger.info(f"Apply {input_file}...")
            iops.apply(input_file)
        except Exception as e:
            Log.handle_exception(
                logger, e, f"Could not apply {os.path.basename(input_file)}"
            )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    iops.write_script(os.path.join(workdir, f"kmhelpers_apply_{timestamp}.sh"))
