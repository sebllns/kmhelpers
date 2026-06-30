"""Build k-mer index command."""

import logging
import os

import click
import yaml

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops

logger = logging.getLogger(__name__)


@click.command(name="plan")
@click.argument(
    "input_file",
    nargs=1,
    required=True,
    type=click.Path(dir_okay=False, file_okay=True, exists=True),
)
@click.option(
    "--work-dir",
    "-w",
    required=False,
    default=".",
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
    "--on-conflict",
    "existing",
    required=False,
    type=click.Choice(
        [
            "fail",
            "register",
            "rename",
            "replace",
            "register_or_replace",
            "register_or_rename",
        ],
        case_sensitive=False,
    ),
    default="fail",
    show_default=True,
    help="⚙   Action when an existing unregistered index folder is found.",
)
@click.option(
    "--offline",
    "-O",
    is_flag=True,
    help="🚩  Skip local path validation (useful when exporting scripts for another machine).",
)
@click.option(
    "--fail-fast",
    "-X",
    "fail_on_error",
    is_flag=True,
    help="🚩  Abort the entire run if any index fails to build, instead of skipping it and continuing.",
)
@click.pass_context
def plan(
    ctx,
    input_file,
    work_dir,
    base_path,
    registry,
    bloom_dir,
    span,
    index_ids,
    reuse_from,
    existing,
    offline,
    fail_on_error,
):
    """Validate paths and preview the build plan from an index definition file.

    📄 INPUT_FILE is an index definition file (.json/.yaml). If it is an index
    definition, indices are previewed directly; if it is a span registry, sub-index
    definition files are resolved from the same directory. Only indices matching
    --name or --span are processed; if neither is specified, all declared indices
    are previewed. The resulting build commands are written to a shell script in
    the working directory.

    Use --offline to skip local path validation when generating scripts for
    another machine.

    Examples:

    \b
    # Preview build plan for a definition file
    kmhelpers plan index.yaml -w /output

    \b
    # Preview only selected indices by name
    kmhelpers plan index.yaml -w /output -n idx1,idx2

    \b
    # Preview only selected k-mer spans
    kmhelpers plan registry.yaml -w /output -s 28
    kmhelpers plan registry.yaml -w /output -s 27,28,29

    \b
    # Reuse parameters from an existing parent index
    kmhelpers plan index.yaml -w /output -n my_index --from parent_index

    \b
    # Resolve sample paths from a base directory
    kmhelpers plan index.yaml -w /output -b /data/samples

    \b
    # Skip path validation (for exporting scripts to another machine)
    kmhelpers plan index.yaml -w /output --offline
    """
    try:
        force = (ctx.obj or {}).get("yes", False)

        abort_msg = "FAILED ('plan')"

        try:
            selected_ids = (
                [id for entry in index_ids for id in entry.split(",") if id]
                if index_ids
                else None
            )
            selected_spans = shared.parse_multiple_ranges(span) if span else None

            assert work_dir, "Required parameter 'work_dir' was not provided."

        except Exception as e:
            pykmhelpers.core.log.Log.handle_exception(logger, e, f"Invalid argument.")
            raise click.ClickException(abort_msg)

        work_dir = os.path.realpath(work_dir)

        if not registry:
            registry = work_dir

        if not bloom_dir:
            bloom_dir = os.path.join(work_dir, "kmindex_data")

        if not offline:
            registry = os.path.realpath(registry)
            bloom_dir = os.path.realpath(bloom_dir)
            if not base_path:
                base_path = os.getcwd()
            base_path = os.path.realpath(base_path)
            if not os.path.isdir(base_path):
                if fail_on_error:
                    click.ClickException(
                        f"Data root directory not found at {base_path}"
                    )
                else:
                    logger.warning(f"Data root directory not found at {base_path}")

        if (
            existing in ("replace", "register_or_replace")
            and not force
            and not click.confirm(
                f"Proceed build with '{existing}' option?", default=True
            )
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
            )
        )

        log_dir = iops.log_dir

        i = 0
        input_files = [input_file]
        for input_file in input_files:
            try:
                logger.info(f"Plan {input_file}...")
                result = iops.run(
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
                pykmhelpers.core.log.Log.handle_exception(
                    logger, e, f"Could not plan {os.path.basename(input_file)}"
                )

        iops.write_script()
        logger.info("SUCCESS ('plan')")
    except (ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('profile')")
