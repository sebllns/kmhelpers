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
    type=click.Path(exists=True),
)
@shared.index_build_options
@shared.index_filter_options
@shared.index_limits_options
@shared.chunk_budget_option
@shared.fail_fast_option
@click.option(
    "--offline",
    "-O",
    is_flag=True,
    help="🚩  Skip local path validation (useful when exporting scripts for another machine).",
)
@click.pass_context
def plan(
    ctx,
    input_file,
    session,
    work_dir,
    base_path,
    index_ids,
    run_ids,
    threads,
    limits,
    safety_margin,
    max_chunks,
    chunk_budget,
    skip_compression,
    keep_previous,
    fail_on_error,
    offline,
):
    """Validate paths and preview the build plan from an index definition file.

    \b
    Input:  COMPOSE_DIR/NAME/SESSION/NAME.yaml written by `compose` or `design`
    Output: shell scripts in BUILD_DIR/assets/SESSION/, validation report in BUILD_DIR/logs/

    BUILD_DIR (-o) is the index directory later passed to `apply` or `build`.
    Only shards matching --shard are processed (all by default); --run
    previews only the matching kmtricks runs, without merging.

    Use --offline to skip local path validation when generating scripts for
    another machine.

    Examples:

    \b
    # Preview build plan for a definition file
    kmhelpers plan coli_db -o coli_build

    \b
    # Preview only selected shards (names or glob patterns)
    kmhelpers plan coli_db -o coli_build --shard coli_g0,coli_g1
    kmhelpers plan coli_db -o coli_build --shard 'coli_g0_*'

    \b
    # Skip path validation (for exporting scripts to another machine)
    kmhelpers plan coli_db -o coli_build --offline
    """

    input_file = shared.resolve_definition(input_file, session)
    try:
        abort_msg = "FAILED ('plan')"

        try:
            selected_ids = shared.split_names(index_ids)
            selected_runs = shared.split_names(run_ids)

            assert work_dir, "Required parameter 'work_dir' was not provided."

        except Exception as e:
            pykmhelpers.core.log.Log.handle_exception(logger, e, f"Invalid argument.")
            raise click.ClickException(abort_msg)

        work_dir = os.path.realpath(work_dir)

        if not offline:
            # Only an explicit --base-path overrides the sample root; otherwise
            # each definition resolves paths against its JSONL header root_path.
            if base_path:
                base_path = os.path.realpath(base_path)
                if not os.path.isdir(base_path):
                    if fail_on_error:
                        raise click.ClickException(
                            f"Data root directory not found at {base_path}"
                        )
                    else:
                        logger.warning(f"Data root directory not found at {base_path}")

        logger.info(f"Working directory: {work_dir}")

        iops = ops.IndexOps(
            config=ops.IndexOpsConfig(
                workdir=work_dir,
                sample_rootpath=base_path,
                kmindex_threads=threads,
                kmindex_skip_compression=skip_compression,
                kmindex_build_from=None,
                filter_names=selected_ids,
                filter_runs=selected_runs,
                keep_previous=keep_previous,
                limits=limits,
                safety_margin=safety_margin,
                max_chunks=max_chunks,
                chunk_budget=chunk_budget,
            )
        )

        log_dir = iops.log_dir

        i = 0
        failed = False
        input_files = [input_file]
        for input_file in input_files:
            try:
                logger.info(f"Plan {input_file}...")
                result = iops.run(
                    input_file,
                    mode=(ops.ApplyMode.DRY_RUN if offline else ops.ApplyMode.PLAN),
                    fail_on_error=fail_on_error,
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
                if result.status in (ops.ApplyStatus.PARTIAL, ops.ApplyStatus.FAILED):
                    failed = True
                    logger.error(f"FAILED to plan {os.path.basename(input_file)}")
            except Exception as e:
                failed = True
                pykmhelpers.core.log.Log.handle_exception(
                    logger, e, f"Could not plan {os.path.basename(input_file)}"
                )

        iops.write_script()
        if failed:
            raise click.ClickException("FAILED ('plan')")
        logger.info("SUCCESS ('plan')")
    except click.ClickException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")
