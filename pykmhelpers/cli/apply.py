"""Run the plan written by `plan`: build, merge and register the indices."""

import logging
import os
from datetime import datetime

import click

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.cli.notify import ExitNotifier, mail
from pykmhelpers.pipeline.index_ops.runner import PlanRunner, describe
from pykmhelpers.pipeline.index_ops.status import PROGRESS_FILE, overall, render

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
    )
    notifier.status = result.status.value
    logger.info(f"Result details written to {report_path}")
    return result


def show_status(input_file: str, work_dir: str, notify: str | None = None) -> str:
    """Print the progress tree of the plan (refreshing progress.yaml, checking
    that RUNNING jobs are still in squeue); with ``notify``, mail it."""
    runner = PlanRunner(work_dir, input_file)
    tree = runner.state.write_progress(check_jobs=True)
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


@click.command(name="apply")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_target_options
@shared.task_option
@shared.pending_option
@shared.status_option
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
    show_progress,
    notify,
    notify_level,
    notify_final,
    fail_on_error,
):
    """Run the plan of a definition file: build, merge and register the indices.

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
    # Run one job (e.g. a SLURM array task), then the merge of its shard
    kmhelpers apply coli_db -o coli_build --task coli_g0_j3
    kmhelpers apply coli_db -o coli_build --task coli_g0_merge

    \b
    # List the jobs not done yet, or where every shard and step stands
    kmhelpers apply coli_db -o coli_build --pending
    kmhelpers apply coli_db -o coli_build --status
    """
    input_file = shared.resolve_definition(input_file, session)
    if status:
        try:
            show_status(input_file, work_dir, notify)
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
