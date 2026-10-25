"""Run the plan written by `plan`: build and publish the indices."""

import logging
import os
import shutil
import time
from datetime import datetime

import click

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.cli.notify import ExitNotifier, mail
from pykmhelpers.pipeline.index_ops.runner import PlanRunner, describe
from pykmhelpers.pipeline.index_ops.progress import ShardDisplay
from pykmhelpers.pipeline.index_ops.status import (
    PROGRESS_FILE,
    RUNNING,
    SUCCESS,
    overall,
    ram_source,
    render,
    squeue_alive,
    step_details,
)

logger = logging.getLogger(__name__)


def run_plan(
    input_file: str,
    work_dir: str,
    notifier: ExitNotifier,
    task_ids=None,
    show_progress: bool = False,
    fail_on_error: bool = False,
) -> ops.ApplyResult:
    """Run the selected jobs of the plan of ``input_file`` in ``work_dir``."""
    runner = PlanRunner(work_dir, input_file)
    jobs = runner.jobs(shared.split_names(task_ids))
    log_dir = os.path.join(os.path.realpath(work_dir), "logs")
    notifier.log_dir = log_dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(log_dir, f"kmhelpers_{notifier.command}_{stamp}.yaml")
    # attached before the run: a killed run still mails its report so far
    notifier.attachments.append(report_path)
    notifier.attachments.append(os.path.join(runner.state.paths.assets, PROGRESS_FILE))
    notifier.progress = lambda shards=None: render(runner.state.write_progress(), shards)
    logger.info(f"Apply {runner.plan_path}: {len(jobs)} job(s)")
    result = runner.run(
        jobs,
        fail_on_error=fail_on_error,
        show_progress=show_progress,
        report_path=report_path,
        on_task_end=notifier.shard_end,
        detailed=bool(task_ids),
    )
    notifier.status = result.status.value
    logger.info(f"Result details written to {report_path}")
    if not task_ids and result.status in (ops.ApplyStatus.SUCCESS, ops.ApplyStatus.NONE):
        # the whole plan ran here: once it is done, nothing needs its locks
        cleanup(runner, quiet=True)
    return result


def cleanup(runner: PlanRunner, quiet: bool = False) -> None:
    """Remove the lock files of the build once its plan is done; never fails.
    ``quiet``: a plan not done (other jobs still to run) is not warned about."""
    try:
        runner.cleanup()
    except ValueError as e:
        if not quiet:
            logger.warning(str(e))
    except Exception as e:
        logger.warning(f"Could not remove the lock files: {e}")


def selected_steps(runner: PlanRunner, task_ids) -> dict[str, set[str]]:
    """The steps of the jobs matching ``task_ids`` (``--task``), per task."""
    steps: dict[str, set[str]] = {}
    for job in runner.jobs(shared.split_names(task_ids)):
        steps.setdefault(job.task, set()).update(job.steps)
    return steps


def show_status(
    input_file: str, work_dir: str, notify: str | None = None, task_ids=None
) -> str:
    """Print the progress tree of the plan (refreshing progress.yaml, checking
    that RUNNING jobs are still in squeue); with ``notify``, mail it. With
    ``task_ids``, only the shards of the matching jobs, their steps in detail
    (job, node, time, RAM and kmtricks phase of a running step)."""
    runner = PlanRunner(work_dir, input_file)
    tree = runner.state.write_progress(check_jobs=True)
    if task_ids:
        state = runner.state
        alive = squeue_alive if shutil.which("squeue") else None
        ram = ram_source(runner.ram_budget())
        details = {
            state.tasks[t]["shard"]: step_details(state, state.tasks[t], steps, alive, ram=ram)
            for t, steps in selected_steps(runner, task_ids).items()
        }
        text = render(tree, list(details), details)
    else:
        text = render(tree)
    click.echo(text)
    result = overall(tree)
    if notify:
        progress = os.path.join(runner.state.paths.assets, PROGRESS_FILE)
        build_dir = runner.state.paths.build_dir
        mail(
            notify,
            f"[kmhelpers build] {result}: {os.path.basename(build_dir)}",
            f"{text}\n\nBUILD_DIR: {build_dir}\nlogs can be found in {os.path.join(build_dir, 'logs')}",
            [progress],
        )
    return result


def watch(input_file: str, work_dir: str, interval: float, task_ids=None) -> int:
    """Draw one line per shard of a cluster build, read again every ``interval``
    seconds, until no shard is running or waiting on a job; 0 when every
    shard is SUCCESS, else 1. Ctrl-C only stops watching. With ``task_ids``,
    only the shards of the matching jobs, their running steps in detail."""
    runner = PlanRunner(work_dir, input_file)
    alive = squeue_alive if shutil.which("squeue") else None
    tasks = list(selected_steps(runner, task_ids)) if task_ids else None
    display = ShardDisplay(
        runner.state,
        tasks,
        alive=alive,
        detailed=bool(task_ids),
        ram=ram_source(runner.ram_budget()),
    )
    try:
        display.start()
        while any(p.state == RUNNING or p.waiting for p in display.shards):
            time.sleep(interval)
            display.update()
    except KeyboardInterrupt:
        logger.info("Stopped watching: the jobs go on")
    finally:
        display.close()
    tree = runner.state.write_progress(check_jobs=True)
    click.echo(render(tree).splitlines()[0])
    if tasks:
        # the shards drawn are those of the selected jobs
        return 0 if all(p.state == SUCCESS for p in display.shards) else 1
    return 0 if overall(tree) == SUCCESS else 1


@click.command(name="apply")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_target_options
@shared.task_option
@shared.pending_option
@shared.status_option
@click.option(
    "--cleanup",
    "do_cleanup",
    is_flag=True,
    hidden=True,
    help="🚩  Hidden, run by the finish job of a cluster build. Once every job of the plan is done, remove the lock files no process "
    "holds (BUILD_DIR/.registry.lock, the layout's), and run nothing. A lock in use "
    "is kept.",
)
@click.option(
    "--interval",
    type=click.FloatRange(min=0.1),
    default=30,
    show_default=True,
    help="⚙   With --status --show-progress: seconds between two reads of a cluster build.",
)
@shared.index_apply_options
@shared.fail_fast_option
@click.pass_context
def apply(
    ctx,
    input_file,
    work_dir,
    session,
    task_ids,
    pending,
    status,
    do_cleanup,
    interval,
    show_progress,
    notify,
    notify_level,
    notify_final,
    fail_on_error,
):
    """Run the plan of a definition file: build and publish the indices.

    \b
    Input:  the INPUT and BUILD_DIR (-o) given to `plan`, which wrote
            BUILD_DIR/assets/SESSION/plan.yaml
    Output: indices in BUILD_DIR/<name>/, registered in BUILD_DIR/index.json

    `apply` takes no sizing option: it runs the scripts of the plan as they
    are, and refuses a plan whose inputs changed since. Every step is checked
    first, so a job can be run again after an interruption. Only what matches
    --task is run (all by default): a shard or its task runs all its jobs, a
    job runs alone.

    Examples:

    \b
    # Run the whole plan
    kmhelpers apply coli_db -o coli_build

    \b
    # Run one job (e.g. a SLURM array task), then the publish job of its shard
    kmhelpers apply coli_db -o coli_build --task coli_g0_j3
    kmhelpers apply coli_db -o coli_build --task coli_g0_publish

    \b
    # List the jobs not done yet, or where every shard and step stands
    kmhelpers apply coli_db -o coli_build --pending
    kmhelpers apply coli_db -o coli_build --status

    \b
    # Follow a cluster build: one line per shard, until it ends
    kmhelpers apply coli_db -o coli_build --status --sp

    \b
    # One shard in detail: job, node, RAM and kmtricks phase of each step
    kmhelpers apply coli_db -o coli_build --status --task coli_g0
    kmhelpers apply coli_db -o coli_build --status --sp --task coli_g0
    kmhelpers apply coli_db -o coli_build --status --task 'coli_g*'   # quoted: no shell glob
    """
    input_file = shared.resolve_definition(input_file, session)
    if task_ids and not shared.split_names(task_ids):
        # --task "" (an empty line of a job list) would select every job
        raise click.UsageError("--task is empty: give a shard, task or job name")
    if do_cleanup:
        try:
            cleanup(PlanRunner(work_dir, input_file))
        except (ValueError, FileNotFoundError) as e:
            raise click.ClickException(str(e))
        return
    if status:
        try:
            if show_progress:
                ctx.exit(watch(input_file, work_dir, interval, task_ids))
            show_status(input_file, work_dir, notify, task_ids)
        except (ValueError, FileNotFoundError) as e:
            raise click.ClickException(str(e))
        return
    notifier = ExitNotifier(
        "apply", None if pending else notify, notify_level, final=notify_final
    )
    try:
        if pending:
            runner = PlanRunner(work_dir, input_file)
            jobs = runner.jobs(shared.split_names(task_ids))
            for job in runner.pending(jobs):
                click.echo(job.name)
                logger.debug(describe(job))
            return
        result = run_plan(
            input_file,
            work_dir,
            notifier,
            task_ids,
            show_progress,
            fail_on_error,
        )
    except (ValueError, FileNotFoundError) as e:
        notifier.status = ops.ApplyStatus.FAILED.value
        raise click.ClickException(str(e))
    except Exception as e:
        notifier.status = ops.ApplyStatus.FAILED.value
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('apply')")
        raise click.ClickException("FAILED ('apply')")

    if result.status in (ops.ApplyStatus.FAILED, ops.ApplyStatus.PARTIAL):
        logger.error(f"{result.status.value} ('apply')")
        raise click.ClickException(f"{result.status.value} ('apply')")
    logger.info("SUCCESS ('apply')")
