"""Run the plan written by `plan`: build, merge and register the indices."""

import logging
import os
from datetime import datetime

import click

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.cli.notify import ExitNotifier
from pykmhelpers.pipeline.index_ops.runner import PlanRunner, describe

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
    logger.info(f"Apply {runner.plan_path}: {len(jobs)} job(s)")
    result = runner.run(
        jobs,
        fail_on_error=fail_on_error,
        show_progress=show_progress,
        report_path=report_path,
    )
    notifier.status = result.status.value
    logger.info(f"Result details written to {report_path}")
    return result


@click.command(name="apply")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_target_options
@shared.task_option
@shared.pending_option
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
    show_progress,
    notify,
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
    # List the jobs not done yet
    kmhelpers apply coli_db -o coli_build --pending
    """
    input_file = shared.resolve_definition(input_file, session)
    notifier = ExitNotifier("apply", None if pending else notify)
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
