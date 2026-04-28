"""Build k-mer index command."""

import atexit
import datetime
import logging
import os
import signal
import sys
import tempfile

import click
import yaml

import pykmhelpers.cli.shared as shared
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.core.constants import KMHELPERS_VERSION
from pykmhelpers.core.log import Log
from pykmhelpers.pipeline.mail_notifier import MailNotifier

logger = logging.getLogger(__name__)


@click.command(name="plan")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--config",
    "-c",
    type=click.Path(file_okay=True, dir_okay=False, exists=True),
    help="📄  Input configuration file (command line arguments take precedence when both are provided).",
)
@click.option(
    "--work-dir",
    "-w",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Working directory path.",
)
@click.option(
    "--base-path",
    "-b",
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
    help="📁  Custom base path to kmindex registry (created if doesn't exist).",
)
@click.option(
    "--bloom-dir",
    "-o",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Custom base path to kmindex Bloom filters directory (created if doesn't exist).",
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
    "--partition-count",
    "-p",
    type=int,
    required=False,
    help="⚙   Override number of partitions.",
)
@click.option(
    "--on-conflict",
    "existing",
    required=False,
    help="⚙   Action when an existing unregistered index folder is found: fail, register, rename,  replace, register_or_replace, register_or_rename (default: fail).",
)
@click.option(
    "--offline",
    "-O",
    is_flag=True,
    help="🚩  Skip local path validation (useful when exporting scripts for another machine).",
)
# @click.option(
#     "--export",
#     "-E",
#     is_flag=True,
#     help="🚩  Export pipeline in a shell script.",
# )
@click.option(
    "--fail-fast",
    "-X",
    "fail_on_error",
    is_flag=True,
    help="🚩  Abort the entire run if any index fails to build, instead of skipping it and continuing.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="🚩  Verbose output.",
)
@click.pass_context
def plan(
    ctx,
    input_files,
    config,
    work_dir,
    base_path,
    registry,
    bloom_dir,
    span,
    index_ids,
    reuse_from,
    partition_count,
    existing,
    offline,
    fail_on_error,
    verbose,
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

    \b
    # Show progress bar during building
    kmhelpers apply index.yaml -w /output --show-progress

    \b
    # Plan: check paths and preview build without executing
    kmhelpers apply index.yaml -w /output --plan

    \b
    # Skip compression of intermediate files
    kmhelpers apply index.yaml -w /output --skip-compression

    \b
    # Resolve sample paths from a base directory
    kmhelpers apply index.yaml -w /output -b /data/samples

    \b
    # Set number of threads and minimizer size
    kmhelpers apply index.yaml -w /output -t 8 --minim-size 12

    \b
    # Load options from a config file (CLI flags take precedence)
    kmhelpers apply index.yaml -c config.yaml
    """

    force = (ctx.obj or {}).get("yes", False)

    abort_msg = "FAILED ('plan')"

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
        selected_ids = (
            [id for entry in index_ids for id in entry.split(",") if id]
            if index_ids
            else None
        )
        selected_spans = shared.parse_multiple_ranges(span) if span else None

        if not work_dir:
            work_dir = config_map.get("work_dir", "kmhelpers_workdir")
        assert work_dir, "Required parameter 'work_dir' was not provided."

        if not registry:
            registry = config_map.get("registry", "")

        if not base_path:
            base_path = config_map.get("base_path", ".")

        if not bloom_dir:
            bloom_dir = config_map.get("bloom_dir")

        if not existing:
            existing = config_map.get("existing", "fail")

        if not reuse_from:
            reuse_from = config_map.get("reuse_from", "")

        if not partition_count:
            partition_count = config_map.get("partition_count", None)

        if not fail_on_error:
            fail_on_error = config_map.get("fail_on_error", False)

    except Exception as e:
        Log.handle_exception(logger, e, f"Invalid argument.")
        raise click.ClickException(abort_msg)

    work_dir = os.path.realpath(work_dir)

    if not registry:
        registry = work_dir
    else:
        registry = os.path.realpath(registry)

    if not bloom_dir:
        bloom_dir = os.path.join(work_dir, "kmindex_data")
    else:
        bloom_dir = os.path.realpath(bloom_dir)

    if not base_path:
        base_path = os.getcwd()

    base_path = os.path.realpath(base_path)

    if not os.path.isdir(base_path):
        if fail_on_error:
            click.ClickException(f"Data root directory not found at {base_path}")
        else:
            logger.warning(f"Data root directory not found at {base_path}")

    if (
        existing in ("replace", "register_or_replace")
        and not force
        and not click.confirm(f"Proceed build with '{existing}' option?", default=True)
    ):
        logger.warning("Build cancelled")
        return

    logger.info(f"Working directory: {work_dir}")

    iops = ops.IndexOps(
        config=ops.IndexOpsConfig(
            workdir=work_dir,
            index_data_folder=bloom_dir,
            registry_dir=os.path.join(work_dir, registry),
            sample_rootpath=base_path,
            kmindex_skip_compression=False,
            kmindex_build_from=reuse_from,
            filter_names=selected_ids,
            filter_spans=selected_spans,
            on_existing=existing,
            fail_on_error=fail_on_error,
            partition_count=partition_count,
        )
    )

    log_dir = iops.log_dir

    i = 0
    for input_file in input_files:
        try:
            logger.info(f"Plan {input_file}...")
            result = iops.apply(
                input_file,
                mode=(ops.ApplyMode.DRY_RUN if offline else ops.ApplyMode.PLAN),
            )
            if result.details:
                details_path = os.path.join(
                    log_dir, f"kmhelpers_plan_{iops.timestamp}_{i}.yaml"
                )
                with open(details_path, "w") as f:
                    yaml.dump(
                        result.details, f, default_flow_style=False, sort_keys=False
                    )
                logger.info(f"Result details written to {details_path}")
                i += 1
        except Exception as e:
            Log.handle_exception(
                logger, e, f"Could not plan {os.path.basename(input_file)}"
            )

    iops.write_script()
