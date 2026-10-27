"""Plan k-mer index builds: decide everything, write the scripts and plan.yaml."""

import logging
import os
import shutil
from typing import Optional

import click
import yaml

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
from pykmhelpers.pipeline.index_ops.cluster import limits_for, load_cluster
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.status import BuildState, active_jobs

logger = logging.getLogger(__name__)


def active_plan_jobs(input_file: str, work_dir: str) -> list[str]:
    """Jobs of the current plan of ``input_file`` still queued or running."""
    paths = BuildPaths.for_input(os.path.realpath(work_dir), input_file)
    plan = {"tasks": {}}
    if os.path.isfile(paths.plan):
        try:
            with open(paths.plan) as f:
                plan = yaml.safe_load(f) or plan
        except (OSError, yaml.YAMLError):
            pass
    return active_jobs(BuildState(plan, paths))


def shown_jobs(active: list[str]) -> str:
    return ", ".join(active[:5]) + (", ..." if len(active) > 5 else "")


def refuse_under_active_jobs(input_file: str, work_dir: str) -> None:
    """Planning again rewrites the scripts and states of every shard: refuse it
    while jobs of the current plan are still queued or running."""
    active = active_plan_jobs(input_file, work_dir)
    if active:
        shown = shown_jobs(active)
        raise click.ClickException(
            f"{len(active)} job(s) of this plan still queued or running ({shown}): "
            f"follow them with `kmhelpers apply {input_file} -o {work_dir} --status --sp`, "
            "or cancel them (scancel) before planning again"
        )


def remove_session_plan(input_file: str, work_dir: str) -> None:
    """``--replan``: remove the plan of the session (``BUILD_DIR/assets/SESSION/``:
    plan.yaml, the folder of each shard, slurm/, progress.yaml) before planning
    again. The indexes, the runs already built (``work/``) and the logs stay."""
    refuse_under_active_jobs(input_file, work_dir)
    assets = BuildPaths.for_input(os.path.realpath(work_dir), input_file).assets
    if os.path.isdir(assets):
        logger.info(f"--replan: removing the previous plan {assets}")
        shutil.rmtree(assets)


def make_plan(
    input_file: str,
    work_dir: str,
    base_path: Optional[str],
    index_ids,
    threads,
    limits,
    safety_margin,
    max_chunks,
    chunk_budget,
    chunks_per_job,
    skip_compression,
    keep_previous,
    fail_on_error: bool,
    offline: bool = False,
    cluster_file: Optional[str] = None,
    notify: Optional[str] = None,
    notify_level: str = "global",
) -> tuple[ops.ApplyResult, Optional[str], str]:
    """Plan ``input_file`` into ``work_dir``; return the result, the plan path
    (None when nothing was planned) and the log directory."""
    work_dir = os.path.realpath(work_dir)
    refuse_under_active_jobs(input_file, work_dir)
    cluster = None
    publish_limits = None
    if cluster_file:
        if limits:
            raise click.ClickException(
                "--limits and --cluster both set the resources: give the job "
                "resources in the cluster file (jobs.build, jobs.publish)"
            )
        cluster = load_cluster(cluster_file)
        limits = limits_for(cluster, "build", safety_margin)
        publish_limits = limits_for(cluster, "publish", safety_margin)
        logger.info(f"Resources from {cluster_file}: build {limits}, publish {publish_limits}")
    # Only an explicit --base-path overrides the sample root; otherwise each
    # definition resolves paths against its JSONL header's root_path.
    if base_path and not offline:
        base_path = os.path.realpath(base_path)
        if not os.path.isdir(base_path):
            if fail_on_error:
                raise click.ClickException(f"Data root directory not found at {base_path}")
            logger.warning(f"Data root directory not found at {base_path}")
    logger.info(f"Working directory: {work_dir}")

    iops = ops.IndexOps(
        config=ops.IndexOpsConfig(
            workdir=work_dir,
            sample_rootpath=base_path,
            kmindex_threads=threads,
            kmindex_skip_compression=skip_compression,
            kmindex_build_from=None,
            filter_names=shared.split_names(index_ids),
            keep_previous=keep_previous,
            limits=limits,
            safety_margin=safety_margin,
            max_chunks=max_chunks,
            chunk_budget=chunk_budget,
            chunks_per_job=chunks_per_job,
            publish_limits=publish_limits,
        )
    )
    logger.info(f"Plan {input_file}...")
    report_path = os.path.join(iops.log_dir, f"kmhelpers_plan_{iops.timestamp}.yaml")
    result = iops.run(
        input_file,
        mode=(ops.ApplyMode.DRY_RUN if offline else ops.ApplyMode.PLAN),
        fail_on_error=fail_on_error,
        report_path=report_path,
    )
    logger.info(f"Plan details written to {report_path}")
    plan_path = None
    if result.status is not ops.ApplyStatus.FAILED:
        plan_path = iops.write_plan(cluster, notify, notify_level)
    return result, plan_path, iops.log_dir


@click.command(name="plan")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_target_options
@shared.index_build_options
@shared.shard_option
@shared.index_limits_options
@shared.chunk_budget_option
@shared.cluster_option
@shared.replan_option
@shared.fail_fast_option
@click.option(
    "--offline",
    "--off",
    is_flag=True,
    help="🚩  Skip local path validation (useful when exporting scripts for another machine).",
)
@click.pass_context
def plan(
    ctx,
    input_file,
    work_dir,
    session,
    base_path,
    threads,
    skip_compression,
    keep_previous,
    chunks_per_job,
    index_ids,
    limits,
    safety_margin,
    max_chunks,
    chunk_budget,
    cluster_file,
    replan,
    fail_on_error,
    offline,
):
    """Decide how to build indices from a definition file, and write the plan.

    \b
    Input:  COMPOSE_DIR/NAME/SESSION/NAME.yaml written by `compose` or `design`
    Output: BUILD_DIR/assets/SESSION/plan.yaml, one directory of scripts per
            shard (BUILD_DIR/assets/SESSION/<shard>/), report in BUILD_DIR/logs/

    Every decision is taken here: partitions, threads, chunks, merges, jobs
    (--chunks-per-job), from the resource limits. `apply` then runs the plan
    as it is, and refuses it if its inputs changed. Only shards matching
    --shard are planned (all by default).

    Use --offline to skip local path validation when generating scripts for
    another machine.

    Examples:

    \b
    # Plan a definition file
    kmhelpers plan coli_db -o coli_build

    \b
    # Plan selected shards (names or glob patterns)
    kmhelpers plan coli_db -o coli_build --shard 'coli_g0_*'

    \b
    # One job per 4 chunks of a shard, e.g. for a SLURM array
    kmhelpers plan coli_db -o coli_build --chunks-per-job 4

    \b
    # Size the plan for the SLURM jobs of cluster.yaml, then submit them
    kmhelpers plan coli_db -o coli_build --cluster cluster.yaml
    bash coli_build/assets/initial/slurm/submit.sh
    """
    given_input = input_file
    input_file = shared.resolve_definition(input_file, session)
    paths = BuildPaths.for_input(os.path.realpath(work_dir), input_file)
    # The input as typed; -s pins the session, as the last one composed can change.
    apply_cmd = f"kmhelpers apply {given_input} -o {work_dir}"
    if os.path.isdir(given_input):
        apply_cmd += f" -s {paths.session}"
    refuse_under_active_jobs(input_file, work_dir)
    if replan:
        remove_session_plan(input_file, work_dir)
    elif os.path.isfile(paths.plan):
        raise click.ClickException(
            f"Session '{paths.session}' already has a plan ({paths.plan}): run it with "
            f"`{apply_cmd}`, or pass --replan to plan again"
        )
    try:
        result, plan_path, _ = make_plan(
            input_file,
            work_dir,
            base_path,
            index_ids,
            threads,
            limits,
            safety_margin,
            max_chunks,
            chunk_budget,
            chunks_per_job,
            skip_compression,
            keep_previous,
            fail_on_error,
            offline,
            cluster_file,
        )
    except click.ClickException:
        raise
    except (ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, "FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")

    if result.status in (ops.ApplyStatus.PARTIAL, ops.ApplyStatus.FAILED):
        raise click.ClickException("FAILED ('plan')")
    if plan_path is None:
        logger.info("NOTHING TO DO ('plan'): the session is already built")
        return
    logger.info(f"Run it with: {apply_cmd}")
    logger.info("SUCCESS ('plan')")
