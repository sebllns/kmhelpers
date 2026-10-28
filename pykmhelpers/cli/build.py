"""Plan then run k-mer index builds in a single command."""

import logging
import os
import shutil
import subprocess
import sys
from typing import Optional

import click
from click.core import ParameterSource

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.cli.apply import run_plan, show_status, watch
from pykmhelpers.cli.notify import ExitNotifier
from pykmhelpers.cli.plan import active_plan_jobs, make_plan, remove_session_plan, shown_jobs
from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.plan_file import check_fresh, load_plan
from pykmhelpers.pipeline.index_ops.runner import PlanRunner

logger = logging.getLogger(__name__)

# seconds between two reads of a cluster build (build --hpc --sp)
WATCH_INTERVAL = 30


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
@shared.replan_option
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
    replan,
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
    active = active_plan_jobs(input_file, work_dir)
    if active and replan:
        remove_session_plan(input_file, work_dir)  # refuses: jobs still active
    if active and cluster_file:
        # submit.sh skips the jobs still queued or running: submit the others
        # (a cancelled or lost job), then follow them all
        logger.info(
            f"{len(active)} job(s) of this plan still queued or running "
            f"({shown_jobs(active)}): not submitted again"
        )
    elif active:
        # rerunning the build of running jobs: follow them, do not plan again
        logger.warning(
            f"{len(active)} job(s) of this plan still queued or running "
            f"({shown_jobs(active)}): following them, nothing planned nor submitted; "
            "pass --hpc to submit the others, cancel them (apply --cancel) to plan again"
        )
        if sys.stdout.isatty():
            ctx.exit(watch(input_file, work_dir, WATCH_INTERVAL))
        show_status(input_file, work_dir)
        return
    plan_file = BuildPaths.for_input(os.path.realpath(work_dir), input_file).plan
    if replan:
        remove_session_plan(input_file, work_dir)
    elif os.path.isfile(plan_file):
        action = _existing_plan(ctx, input_file, work_dir, cluster_file)
        if action == "done":
            _already_built(input_file, work_dir)
            return
        if action == "submit":
            _submit(
                input_file, work_dir,
                os.path.join(os.path.dirname(plan_file), "slurm", "submit.sh"),
                show_progress,
            )
            if show_progress:
                ctx.exit(watch(input_file, work_dir, WATCH_INTERVAL))
            return
        notifier = ExitNotifier("build", notify, notify_level, final=notify_final)
        notifier.log_dir = os.path.join(os.path.realpath(work_dir), "logs")
        _apply_locally(input_file, work_dir, notifier, show_progress)
        return
    if cluster_file:
        _build_on_cluster(
            ctx, input_file, work_dir, base_path, threads, limits, safety_margin,
            max_chunks, chunk_budget, chunks_per_job, skip_compression,
            keep_previous, cluster_file, notify, notify_level, show_progress,
        )
        if show_progress:
            ctx.exit(watch(input_file, work_dir, WATCH_INTERVAL))
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

    if result.status is ops.ApplyStatus.FAILED:
        notifier.status = ops.ApplyStatus.FAILED.value
        logger.error("FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")
    if plan_path is None and result.status is not ops.ApplyStatus.PARTIAL:
        # nothing happened: no mail
        notifier.recipient = None
        _already_built(input_file, work_dir)
        return
    if result.status is ops.ApplyStatus.PARTIAL:
        # Some operations were dropped: do not build what is known incomplete
        notifier.status = ops.ApplyStatus.PARTIAL.value
        logger.error("PARTIAL ('plan')")
        raise PartialError("PARTIAL ('plan')")
    logger.info("SUCCESS ('plan')")
    _show_summary(result, input_file, work_dir)
    if not shared.confirm(ctx, "Build it?", default=True, unattended=True):
        notifier.recipient = None
        _decline(input_file, work_dir)

    # --- Step 2: apply ---
    _apply_locally(input_file, work_dir, notifier, show_progress)


def _apply_locally(input_file: str, work_dir: str, notifier: ExitNotifier, show_progress: bool) -> None:
    """Run the plan here; fail loudly (``build`` is the high-level command)."""
    try:
        pykmhelpers.core.log.Log.step(logger, f"STEP 2: Apply {input_file}")
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
    ctx, input_file, work_dir, base_path, threads, limits, safety_margin, max_chunks,
    chunk_budget, chunks_per_job, skip_compression, keep_previous, cluster_file,
    notify, notify_level, show_progress=False,
) -> None:
    """Plan for the jobs of ``cluster_file``, then run its submit.sh and exit:
    the jobs build the indices; ``apply --status --sp`` follows them."""
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
    if result.status is ops.ApplyStatus.FAILED:
        raise click.ClickException("FAILED ('plan')")
    if result.status is ops.ApplyStatus.PARTIAL:
        # Some operations were dropped: do not submit what is known incomplete
        raise PartialError("PARTIAL ('plan'): nothing submitted")
    if plan_path is None:
        _already_built(input_file, work_dir)
        return
    logger.info("SUCCESS ('plan')")
    _show_summary(result, input_file, work_dir, on_cluster=True)
    if not shared.confirm(ctx, "Submit it?", default=True, unattended=True):
        _decline(input_file, work_dir)
    _submit(
        input_file, work_dir,
        os.path.join(os.path.dirname(plan_path), "slurm", "submit.sh"),
        show_progress,
    )


def _show_summary(result, input_file: str, work_dir: str, on_cluster: bool = False) -> None:
    """What the new plan builds: shards, samples, runs and estimated size, against
    the free space of BUILD_DIR."""
    summary = result.details.get("summary", {})
    totals = summary.get("totals", {})
    if not totals:
        return
    logger.info(
        f"To build: {totals['shards']} shard(s), {totals['samples']} sample(s), "
        f"{totals['runs']} kmtricks run(s), estimated size {totals['est_size']}"
    )
    for span, s in summary.get("spans", {}).items():
        logger.info(f"  span {span}: {s['shards']} shard(s), {s['samples']} sample(s), {s['est_size']}")
    if on_cluster:
        jobs = PlanRunner(work_dir, input_file).jobs()
        logger.info(f"  {len(jobs)} build/publish job(s), then a finish job")
    free = shutil.disk_usage(work_dir).free
    est = shared.parse_size(totals["est_size"], "estimated size")
    logger.info(f"Free space in {work_dir}: {ByteCounter.auto(free)}")
    if est > free:
        logger.warning(
            "The estimated size is over the free space, and merges need more "
            "than the final size while they run"
        )


def _decline(input_file: str, work_dir: str) -> None:
    """Build declined: remove the new plan, so that a later build plans and asks again."""
    remove_session_plan(input_file, work_dir)
    logger.info("Nothing built")
    raise click.Abort()


def _submit(input_file: str, work_dir: str, submit: str, watching: bool = False) -> None:
    """Run the plan's submit.sh: it submits what is not done yet."""
    pykmhelpers.core.log.Log.step(logger, f"STEP 2: Submit {submit}")
    proc = subprocess.run(["bash", submit], capture_output=True, text=True)
    for line in (proc.stdout + proc.stderr).splitlines():
        logger.info(line)
    if proc.returncode != 0:
        raise click.ClickException(f"FAILED ('submit'): {submit} exited {proc.returncode}")
    status = f"kmhelpers apply {input_file} -o {work_dir} --status"
    logger.info("Submitted: the jobs run on SLURM, independently of this command")
    if watching:
        logger.info("Ctrl-C only stops following them: the jobs go on")
    logger.info(f"Follow them (again) with: {status} --sp")
    logger.info(f"Details of shards (RAM, kmtricks step, job ids): {status} --sp --task SHARD (or a quoted glob)")


# options taking build decisions: not used when the existing plan is run
_PLAN_OPTIONS = {
    "base_path": "--base-path",
    "threads": "--threads",
    "skip_compression": "--skip-compression",
    "keep_previous": "--keep-previous",
    "chunks_per_job": "--chunks-per-job",
    "limits": "--limits",
    "safety_margin": "--safety-margin",
    "max_chunks": "--max-chunks",
    "chunk_budget": "--chunk-budget",
    "notify": "--notify",
    "notify_level": "--notify-level",
}


def _existing_plan(ctx, input_file: str, work_dir: str, cluster_file: Optional[str]) -> str:
    """What to do with the existing plan of the session: ``done``, ``submit``
    (a cluster plan) or ``local``; refuse a plan that cannot be used as it is."""
    paths = BuildPaths.for_input(os.path.realpath(work_dir), input_file)
    plan = load_plan(paths.plan)
    replan = "pass --replan to plan again"
    try:
        check_fresh(plan, input_file)
    except ValueError as e:
        raise click.ClickException(f"{str(e).split(' Run ')[0]} {replan}")
    on_cluster = bool(plan.get("cluster"))
    if cluster_file and not on_cluster:
        raise click.ClickException(f"The plan of session '{paths.session}' is not for a cluster: {replan}")
    if on_cluster and not cluster_file:
        raise click.ClickException(
            f"The plan of session '{paths.session}' is for a cluster: pass --hpc to submit it, or {replan}"
        )
    logger.info(
        f"Session '{paths.session}' already has a plan ({plan.get('created')}): it is used "
        f"as it is, not planned again ({replan})"
    )
    unused = [
        flag for name, flag in _PLAN_OPTIONS.items()
        if ctx.get_parameter_source(name) is not ParameterSource.DEFAULT
        and (name not in ("notify", "notify_level") or on_cluster)
    ]
    if on_cluster and cluster_file:
        source = (plan.get("cluster") or {}).get("source")
        if source and os.path.realpath(cluster_file) != source:
            unused.append(f"--hpc {cluster_file} (the plan uses {source})")
    if unused:
        logger.warning(f"Not used, the plan is not made again: {', '.join(unused)}")
    if not PlanRunner(work_dir, input_file).pending():
        return "done"
    return "submit" if on_cluster else "local"


def _already_built(input_file: str, work_dir: str) -> None:
    """A session already built: say so, and show the status of its last plan."""
    logger.info("NOTHING TO DO ('build'): the session is already built, nothing submitted")
    try:
        show_status(input_file, work_dir)
    except (ValueError, FileNotFoundError) as e:
        logger.debug(f"No status to show: {e}")
