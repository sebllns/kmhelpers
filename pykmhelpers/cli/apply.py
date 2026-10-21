"""Build k-mer index command."""

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


@click.command(name="apply")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_build_options
@shared.index_filter_options
@shared.index_limits_options
@shared.chunk_budget_option
@shared.index_apply_options
@shared.fail_fast_option
@click.pass_context
def apply(
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
    show_progress,
    fail_on_error,
    notify,
):
    """Apply changes and build indices from definition files.

    \b
    Input:  COMPOSE_DIR/NAME/SESSION/NAME.yaml written by `compose` or `design`
    Output: indices in BUILD_DIR/<name>/, registered in BUILD_DIR/index.json

    BUILD_DIR (-o) is the index directory, reused across builds and passed to
    `query -r`. Parent indices are built automatically when required. Only
    shards matching --shard are processed (all by default); --run builds only
    the matching kmtricks runs, without merging.

    Examples:

    \b
    # Build all indices declared in a definition file
    kmhelpers apply coli_db -o coli_build

    \b
    # Build only selected shards (names or glob patterns)
    kmhelpers apply coli_db -o coli_build --shard coli_g0,coli_g1
    kmhelpers apply coli_db -o coli_build --shard 'coli_g0_*'

    \b
    # Build one chunk (e.g. a SLURM array task), then merge the shard
    kmhelpers apply coli_db -o coli_build --run coli_g0_p1_initial_chunk3
    kmhelpers apply coli_db -o coli_build --shard coli_g0_p1

    \b
    # Show progress
    kmhelpers apply coli_db -o coli_build --show-progress
    """

    input_file = shared.resolve_definition(input_file, session)

    abort_msg = "Command 'apply' aborted."
    attachements = []
    log_dir = "UNDEFINED_LOG_DIR"

    if pykmhelpers.core.log.Log.log_file:
        attachements.append(pykmhelpers.core.log.Log.log_file)

    # Notification setup
    _notify_state = {
        "status": ops.ApplyStatus.NONE.value,
        "recipient": notify,
        "sender": "kmhelpers@groupes.renater.fr",
    }

    # def _build_attachment() -> str:
    #     # TODO: fill with details
    #     tmp = tempfile.NamedTemporaryFile(
    #         mode="w", suffix=".txt", delete=False, prefix="kmhelpers_apply_"
    #     )
    #     tmp.write("TEST")
    #     tmp.close()
    #     return tmp.name

    def _send_notification():
        recipient = _notify_state.get("recipient")
        if not recipient:
            return
        status = _notify_state["status"]
        if status == "NONE":
            status = "CANCELLED"
        # attachment = _build_attachment()
        try:
            pykmhelpers.pipeline.mail_notifier.MailNotifier(dry_run=False).send(
                to=recipient,
                subject=f"[kmhelpers apply] {status}",
                body=f"kmhelpers apply exited with status: {status}\nkmindex logs can be found in {log_dir}",
                sender=_notify_state["sender"],
                attachments=attachements,
            )
        except Exception as e:
            logger.warning(f"Could not send notification email: {e}")
        # finally:
        #     os.unlink(attachment)

    def _handle_sigterm(sig, frame):
        _notify_state["status"] = ops.ApplyStatus.NONE.value
        sys.exit(1)

    if notify:
        atexit.register(_send_notification)
        signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        selected_ids = shared.split_names(index_ids)
        selected_runs = shared.split_names(run_ids)
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, f"Invalid argument.")
        raise click.ClickException(abort_msg)

    work_dir = os.path.realpath(work_dir or "build")

    # Only an explicit --base-path overrides the sample root; otherwise each
    # definition resolves paths against its JSONL header's root_path.
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

    apply_mode = (
        ops.ApplyMode.APPLY_SHOW_PROGRESS if show_progress else ops.ApplyMode.APPLY
    )

    i = 0
    failed = False

    if not input_file:
        raise ValueError(f"Definition file not provided")

    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Definition file {input_file} not found")

    input_files = [input_file]
    for input_file in input_files:
        try:
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

            logger.info(f"Apply {input_file}...")
            result = iops.run(input_file, apply_mode, fail_on_error=fail_on_error)
            _notify_state["status"] = result.status.value
            if result.details:
                details_path = os.path.join(
                    log_dir, f"kmhelpers_apply_{iops.timestamp}_{i}.yaml"
                )
                with open(details_path, "w") as f:
                    yaml.dump(
                        result.details, f, default_flow_style=False, sort_keys=False
                    )
                attachements.append(details_path)
                logger.info(f"Result details written to {details_path}")
                i += 1
            if result.status is ops.ApplyStatus.FAILED:
                failed = True
                logger.error("FAILED ('apply')")
            else:
                logger.info("SUCCESS ('apply')")
        except Exception as e:
            failed = True
            _notify_state["status"] = ops.ApplyStatus.FAILED.value
            pykmhelpers.core.log.Log.handle_exception(
                logger, e, f"Could not apply {os.path.basename(input_file)}"
            )

    if failed:
        raise click.ClickException("FAILED ('apply')")
