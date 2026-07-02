"""Validate paths then build k-mer indices in a single command."""

import atexit
import logging
import os
import signal
import sys

import click
import yaml

import pykmhelpers.cli.shared as shared
import pykmhelpers.core.log
import pykmhelpers.pipeline.index_ops as ops
import pykmhelpers.pipeline.mail_notifier

logger = logging.getLogger(__name__)


@click.command(name="build")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@click.option(
    "--work-dir",
    "-w",
    required=False,
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Working directory path.",
)
@click.option(
    "--base-path",
    "-b",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Base path to resolve relative sample paths.",
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
    help="⚙   Build only selected span (e.g., --span 28, --span 27,28,29, --span 27-30).",
)
@click.option(
    "--name",
    "-n",
    "index_ids",
    multiple=True,
    required=False,
    help="⚙   Index IDs to build. Can be repeated (-n id1 -n id2) or comma-separated (-n id1,id2).",
)
@click.option(
    "--from",
    "reuse_from",
    required=False,
    help="⚙   Parent index ID to reuse parameters from.",
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
    "--minim-size",
    type=int,
    required=False,
    help="⚙   Minimizer size (4-15, default: 10).",
)
@click.option(
    "--threads",
    "-t",
    type=int,
    required=False,
    help="⚙   Number of threads (default: 1).",
)
@click.option(
    "--partition-count",
    "-p",
    type=int,
    required=False,
    help="⚙   Override number of partitions.",
)
@click.option(
    "--skip-compression",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Skip compression of intermediate files during index building.",
)
@click.option(
    "--show-progress",
    is_flag=True,
    default=False,
    show_default=True,
    help="🚩  Show a progress bar during index building.",
)
@click.option(
    "--fail-fast",
    "-X",
    "fail_on_error",
    is_flag=True,
    help="🚩  Abort the entire run if any index fails to build.",
)
@click.option(
    "--notify",
    required=False,
    metavar="EMAIL",
    help="📧  Send an email notification on exit (success, failure, or timeout).",
)
@click.pass_context
def build(
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
    minim_size,
    threads,
    partition_count,
    skip_compression,
    show_progress,
    fail_on_error,
    notify,
):
    """Validate paths then build indices from definition files.

    Runs the pipeline [plan → apply] in a single command.

    \b
    Input:  index definition file(s) (.json/.yaml) from `compose`
    Output: built k-mer index in WORK_DIR/, registered in WORK_DIR/index.json

    \b
    Steps:
      1. plan  - validate paths and write a build script to WORK_DIR/assets/
      2. apply - execute the build and register all indices

    Examples:

    \b
    # Plan then build all indices in a definition file
    kmhelpers build index.yaml -w /output

    \b
    # Filter by name or span
    kmhelpers build index.yaml -w /output -n idx1,idx2
    kmhelpers build registry.yaml -w /output -s 28

    \b
    # Set threads and show progress
    kmhelpers build index.yaml -w /output -t 8 --show-progress
    """
    force = (ctx.obj or {}).get("yes", False)

    abort_msg = "Command 'build' aborted."
    attachments = []
    log_dir = "UNDEFINED_LOG_DIR"

    if pykmhelpers.core.log.Log.log_file:
        attachments.append(pykmhelpers.core.log.Log.log_file)

    _notify_state = {
        "status": ops.ApplyStatus.NONE.value,
        "recipient": notify,
        "sender": "kmhelpers@groupes.renater.fr",
    }

    def _send_notification():
        recipient = _notify_state.get("recipient")
        if not recipient:
            return
        status = _notify_state["status"]
        if status == "NONE":
            status = "CANCELLED"
        try:
            pykmhelpers.pipeline.mail_notifier.MailNotifier(dry_run=False).send(
                to=recipient,
                subject=f"[kmhelpers build] {status}",
                body=f"kmhelpers build exited with status: {status}\nkmindex logs can be found in {log_dir}",
                sender=_notify_state["sender"],
                attachments=attachments,
            )
        except Exception as e:
            logger.warning(f"Could not send notification email: {e}")

    def _handle_sigterm(sig, frame):
        _notify_state["status"] = ops.ApplyStatus.NONE.value
        sys.exit(1)

    if notify:
        atexit.register(_send_notification)
        signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        selected_ids = [id for entry in index_ids for id in entry.split(",") if id]
        selected_spans = shared.parse_multiple_ranges(span) if span else None

        assert work_dir, "Required parameter 'work_dir' was not provided."

    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, "Invalid argument.")
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
            raise click.ClickException(f"Data root directory not found at {base_path}")
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
            minimizer_length=int(minim_size) if minim_size else 10,
            sample_rootpath=base_path,
            kmindex_threads=threads or 1,
            kmindex_skip_compression=skip_compression,
            kmindex_build_from=reuse_from,
            filter_names=selected_ids,
            filter_spans=selected_spans,
            on_existing=existing,
            fail_on_error=fail_on_error,
            partition_count=partition_count,
        )
    )

    log_dir = iops.log_dir

    # --- Step 1: plan ---
    try:
        logger.info(f"Plan {input_file}...")
        result = iops.run(input_file, mode=ops.ApplyMode.PLAN)
        if result.details:
            details_path = os.path.join(
                log_dir, f"kmhelpers_plan_{iops.timestamp}.yaml"
            )
            with open(details_path, "w") as f:
                yaml.dump(result.details, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Plan details written to {details_path}")
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(
            logger, e, f"Could not plan {os.path.basename(input_file)}"
        )
        raise click.ClickException("FAILED ('plan')")

    iops.write_script()
    logger.info("SUCCESS ('plan')")

    # --- Step 2: apply ---
    apply_mode = (
        ops.ApplyMode.APPLY_SHOW_PROGRESS if show_progress else ops.ApplyMode.APPLY
    )

    try:
        logger.info(f"Apply {input_file}...")
        result = iops.run(input_file, apply_mode)
        _notify_state["status"] = result.status.value
        if result.details:
            details_path = os.path.join(
                log_dir, f"kmhelpers_apply_{iops.timestamp}.yaml"
            )
            with open(details_path, "w") as f:
                yaml.dump(result.details, f, default_flow_style=False, sort_keys=False)
            attachments.append(details_path)
            logger.info(f"Apply details written to {details_path}")
        logger.info("SUCCESS ('apply')")
    except Exception as e:
        _notify_state["status"] = ops.ApplyStatus.FAILED.value
        pykmhelpers.core.log.Log.handle_exception(
            logger, e, f"Could not apply {os.path.basename(input_file)}"
        )
