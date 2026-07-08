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


class PartialError(click.ClickException):
    """A build that only partially succeeded.

    Exits with code 2 to distinguish a partial build (some sub-index
    operations failed while others succeeded) from a total failure
    (``click.ClickException`` -> exit 1) and from success (exit 0).
    """

    exit_code = 2


@click.command(name="build")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_build_options
@shared.index_apply_options
@click.pass_context
def build(
    ctx,
    input_file,
    work_dir,
    base_path,
    minim_size,
    threads,
    partition_count,
    limits,
    safety_margin,
    skip_compression,
    show_progress,
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
    kmhelpers build index.yaml -o build

    \b
    # Set threads and show progress
    kmhelpers build index.yaml -o build -t 8 --show-progress
    """

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
        assert work_dir, "Required parameter 'work_dir' was not provided."

    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, "Invalid argument.")
        raise click.ClickException(abort_msg)

    work_dir = os.path.realpath(work_dir)

    registry = work_dir
    input_file_dir = os.path.basename(os.path.dirname(os.path.realpath(input_file)))
    bloom_dir = os.path.join(work_dir, "kmindex_data", input_file_dir)

    if os.path.isdir(bloom_dir):
        raise click.ClickException(
            f"Bloom filter directory already exists at {bloom_dir}"
        )

    if not base_path:
        base_path = os.getcwd()
    base_path = os.path.realpath(base_path)

    if not os.path.isdir(base_path):
        raise click.ClickException(f"Data root directory not found at {base_path}")

    logger.info(f"Working directory: {work_dir}")

    iops = ops.IndexOps(
        config=ops.IndexOpsConfig(
            workdir=work_dir,
            index_data_folder=bloom_dir,
            registry_dir=os.path.join(work_dir, registry),
            minimizer_length=int(minim_size) if minim_size else 10,
            sample_rootpath=base_path,
            kmindex_threads=threads,
            kmindex_skip_compression=skip_compression,
            kmindex_build_from=None,
            filter_names=None,
            filter_spans=None,
            on_existing="fail",
            partition_count=partition_count,
            safety_margin=0.75,
        )
    )

    log_dir = iops.log_dir

    # --- Step 1: plan ---
    try:
        pykmhelpers.core.log.Log.step(logger, f"STEP 1: Plan {input_file}")
        result = iops.run(input_file, mode=ops.ApplyMode.PLAN, fail_on_error=False)
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
    if result.status is ops.ApplyStatus.FAILED:
        logger.error("FAILED ('plan')")
        raise click.ClickException("FAILED ('plan')")
    elif result.status is ops.ApplyStatus.PARTIAL:
        # A partial plan means some operations were dropped; do not proceed
        # to apply a build we already know is incomplete -- fail directly.
        _notify_state["status"] = ops.ApplyStatus.PARTIAL.value
        logger.error("PARTIAL ('plan')")
        raise PartialError("PARTIAL ('plan')")
    elif result.status is ops.ApplyStatus.NONE:
        logger.info("NOTHING TO DO ('plan')")
    else:
        logger.info("SUCCESS ('plan')")

    # --- Step 2: apply ---
    apply_mode = (
        ops.ApplyMode.APPLY_SHOW_PROGRESS if show_progress else ops.ApplyMode.APPLY
    )

    try:
        pykmhelpers.core.log.Log.step(logger, f"STEP 2: Apply {input_file}")
        # 'build' is the high-level command: always fail loudly rather than
        # skipping a failed index and exiting 0.
        result = iops.run(input_file, apply_mode, fail_on_error=True)
        _notify_state["status"] = result.status.value
        if result.details:
            details_path = os.path.join(
                log_dir, f"kmhelpers_apply_{iops.timestamp}.yaml"
            )
            with open(details_path, "w") as f:
                yaml.dump(result.details, f, default_flow_style=False, sort_keys=False)
            attachments.append(details_path)
            logger.info(f"Apply details written to {details_path}")
        if result.status is ops.ApplyStatus.FAILED:
            logger.error("FAILED ('apply')")
            raise click.ClickException("FAILED ('apply')")
        elif result.status is ops.ApplyStatus.PARTIAL:
            logger.warning("PARTIAL ('apply')")
            raise PartialError("PARTIAL ('apply')")
        elif result.status is ops.ApplyStatus.NONE:
            logger.info("NOTHING TO DO ('apply')")
        else:
            logger.info("SUCCESS ('apply')")
    except click.ClickException:
        raise
    except Exception as e:
        _notify_state["status"] = ops.ApplyStatus.FAILED.value
        pykmhelpers.core.log.Log.handle_exception(
            logger, e, f"Could not apply {os.path.basename(input_file)}"
        )
        raise click.ClickException("FAILED ('apply')")
