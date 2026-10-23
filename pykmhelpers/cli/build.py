"""Plan then run k-mer index builds in a single command."""

import logging
import os
import subprocess

import click

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.cli.apply import run_plan
from pykmhelpers.cli.notify import ExitNotifier
from pykmhelpers.cli.plan import make_plan

logger = logging.getLogger(__name__)


class PartialError(click.ClickException):
    """A build that only partially succeeded.

    Exits with code 2 to distinguish a partial build (some sub-index
    operations failed while others succeeded) from a total failure
    (``click.ClickException`` -> exit 1) and from success (exit 0).
    """

    exit_code = 2


@click.command(name="build")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_target_options
@shared.index_build_options
@shared.index_apply_options
@shared.index_limits_options
@shared.chunk_budget_option
@shared.cluster_option
@click.pass_context
def build(
    ctx,
    input_file,
    work_dir,
    session,
    base_path,
    threads,
    skip_compression,
    keep_previous,
    chunks_per_job,
    show_progress,
    notify,
    notify_level,
    notify_final,
    limits,
    safety_margin,
    max_chunks,
    chunk_budget,
    cluster_file,
):
    """Plan then build indices from definition files.

    Runs the pipeline [plan → apply] in a single command.

    \b
    Input:  COMPOSE_DIR/NAME/SESSION/NAME.yaml written by `compose` or `design`
    Output: indices in BUILD_DIR/<name>/, registered in BUILD_DIR/index.json

    BUILD_DIR (-o) is the index directory, reused across builds and passed to
    `query -r`. A given SESSION can only be built once into a BUILD_DIR.

    \b
    Steps:
      1. plan  - decide everything, write BUILD_DIR/assets/SESSION/plan.yaml
                 and the scripts of every shard
      2. apply - run the plan and register all indices

    Examples:

    \b
    # Build the index defined in session "initial"
    kmhelpers build coli_db -o coli_build

    \b
    # Add an update session to the same index directory
    kmhelpers build coli_db -s update -o coli_build

    \b
    # On a cluster: plan for the jobs of cluster.yaml, submit them, and exit;
    # mail the end of every shard and of the build
    kmhelpers build coli_db -o coli_build --hpc cluster.yaml \\
        --notify you@example.com --notify-level shard
    kmhelpers apply coli_db -o coli_build --status
    """
    input_file = shared.resolve_definition(input_file, session)
    if cluster_file:
        _build_on_cluster(
            input_file, work_dir, base_path, threads, limits, safety_margin,
            max_chunks, chunk_budget, chunks_per_job, skip_compression,
            keep_previous, cluster_file, notify, notify_level,
        )
        return
    notifier = ExitNotifier("build", notify, notify_level, final=notify_final)

    # --- Step 1: plan ---
    try:
        pykmhelpers.core.log.Log.step(logger, f"STEP 1: Plan {input_file}")
        result, plan_path, log_dir = make_plan(
            input_file,
            work_dir,
            base_path,
            None,
            threads,
            limits,
            safety_margin,
            max_chunks,
            chunk_budget,
            chunks_per_job,
            skip_compression,
            keep_previous,
            fail_on_error=False,
        )
        notifier.log_dir = log_dir
    except click.ClickException:
        raise
    except Exception as e:
        notifier.status = ops.ApplyStatus.FAILED.value
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")

    if result.status is ops.ApplyStatus.FAILED or plan_path is None:
        notifier.status = ops.ApplyStatus.FAILED.value
        logger.error("FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")
    if result.status is ops.ApplyStatus.PARTIAL:
        # Some operations were dropped: do not build what is known incomplete
        notifier.status = ops.ApplyStatus.PARTIAL.value
        logger.error("PARTIAL ('plan')")
        raise PartialError("PARTIAL ('plan')")
    logger.info("SUCCESS ('plan')")

    # --- Step 2: apply ---
    try:
        pykmhelpers.core.log.Log.step(logger, f"STEP 2: Apply {input_file}")
        # 'build' is the high-level command: always fail loudly rather than
        # skipping a failed index and exiting 0.
        result = run_plan(
            input_file, work_dir, notifier, show_progress=show_progress, fail_on_error=True
        )
    except click.ClickException:
        raise
    except Exception as e:
        notifier.status = ops.ApplyStatus.FAILED.value
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('apply')")
        raise click.ClickException("FAILED ('apply')")

    if result.status is ops.ApplyStatus.FAILED:
        logger.error("FAILED ('apply')")
        raise click.ClickException("FAILED ('apply')")
    if result.status is ops.ApplyStatus.PARTIAL:
        logger.warning("PARTIAL ('apply')")
        raise PartialError("PARTIAL ('apply')")
    if result.status is ops.ApplyStatus.NONE:
        logger.info("NOTHING TO DO ('apply')")
    else:
        logger.info("SUCCESS ('apply')")


def _build_on_cluster(
    input_file, work_dir, base_path, threads, limits, safety_margin, max_chunks,
    chunk_budget, chunks_per_job, skip_compression, keep_previous, cluster_file,
    notify, notify_level,
) -> None:
    """Plan for the jobs of ``cluster_file``, then run its submit.sh and exit:
    the jobs build the indices; ``apply --status`` follows them."""
    try:
        pykmhelpers.core.log.Log.step(logger, f"STEP 1: Plan {input_file}")
        result, plan_path, _ = make_plan(
            input_file,
            work_dir,
            base_path,
            None,
            threads,
            limits,
            safety_margin,
            max_chunks,
            chunk_budget,
            chunks_per_job,
            skip_compression,
            keep_previous,
            fail_on_error=False,
            cluster_file=cluster_file,
            notify=notify,
            notify_level=notify_level,
        )
    except click.ClickException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")
    if result.status is ops.ApplyStatus.FAILED or plan_path is None:
        raise click.ClickException("FAILED ('plan')")
    if result.status is ops.ApplyStatus.PARTIAL:
        # Some operations were dropped: do not submit what is known incomplete
        raise PartialError("PARTIAL ('plan'): nothing submitted")
    logger.info("SUCCESS ('plan')")

    submit = os.path.join(os.path.dirname(plan_path), "slurm", "submit.sh")
    pykmhelpers.core.log.Log.step(logger, f"STEP 2: Submit {submit}")
    proc = subprocess.run(["bash", submit], capture_output=True, text=True)
    for line in (proc.stdout + proc.stderr).splitlines():
        logger.info(line)
    if proc.returncode != 0:
        raise click.ClickException(f"FAILED ('submit'): {submit} exited {proc.returncode}")
    logger.info(f"Submitted. Follow it with: kmhelpers apply {input_file} -o {work_dir} --status")
