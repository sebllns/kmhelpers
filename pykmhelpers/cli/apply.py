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


def _parse_spans(spans):
    """Parse span arguments supporting multiple formats:
    - Single values: --span 28
    - Comma-separated: --span 27,28,29
    - Range notation: --span [27-30] or --span 27-30
    """
    result = []
    for item in spans:
        # Handle range notation [27-30] or 27-30
        item = item.strip(" []-")
        if "-" in item:
            # Range notation: 27-30
            try:
                start, end = item.split("-")
                result.extend(
                    i for i in range(int(start.strip()), int(end.strip()) + 1)
                )
            except ValueError:
                result.append(item)
        else:
            # Comma-separated or single value
            result.extend(int(s.strip()) for s in item.split(","))
    return result


@click.command(name="apply")
@click.argument("input_file", nargs=1, required=True, type=click.Path(exists=True))
@shared.index_build_options
@shared.index_filter_options
@shared.index_limits_options
@shared.index_apply_options
@shared.fail_fast_option
@click.option(
    "--registry",
    "-r",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Custom base path to kmindex registry (created if doesn't exist).",
)
@click.option(
    "--bloom-dir",
    "-bl",
    required=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="📁  Custom base path to kmindex Bloom filters directory (created if doesn't exist).",
)
@click.option(
    "--from",
    "reuse_from",
    required=False,
    help="⚙   Parent index ID to reuse parameters from. Takes precedence over parent_index that can be specified in definition file.",
)
@click.option(
    "--existing",
    required=False,
    help="⚙   Action when an existing unregistered index folder is found: fail, register, rename, replace, register_or_replace, register_or_rename (default: fail).",
)
@click.pass_context
def apply(
    ctx,
    input_file,
    work_dir,
    base_path,
    registry,
    bloom_dir,
    span,
    index_ids,
    reuse_from,
    minim_size,
    threads,
    partition_count,
    limits,
    safety_margin,
    existing,
    skip_compression,
    show_progress,
    fail_on_error,
    notify,
):
    """Apply changes and build indices from definition files.

    \b
    Input:  index definition file(s) (.json/.yaml) from `compose`
    Output: built k-mer index in WORK_DIR/, registered in WORK_DIR/index.json

    📄 input_file are one or more index definition files (.json/.yaml). For each file,
    the declared indices are built and registered. If the file type is an index definition,
    indices are built directly; if it is a span registry, sub-index definition files are
    resolved from the same directory and merged into the named indices after building.
    Parent indices are built automatically when required. Only indices matching --name or
    --span are processed; if neither is specified, all declared indices are built.

    Examples:

    \b
    # Build all indices declared in a definition file
    kmhelpers apply index.yaml -o /output

    \b
    # Build only selected indices by name (comma-separated or repeated flags)
    kmhelpers apply index.yaml -o /output -n idx1,idx2
    kmhelpers apply index.yaml -o /output -n idx1 -n idx2

    \b
    # Build only selected k-mer spans from a span registry
    kmhelpers apply registry.yaml -o /output -s 28
    kmhelpers apply registry.yaml -o /output -s 27,28,29

    \b
    # Dry run: print build commands without executing
    kmhelpers apply index.yaml -o /output --dry-run

    \b
    # Reuse parameters from an existing parent index
    kmhelpers apply index.yaml -o /output -n my_index --from parent_index

    \b
    # Show progress bar during building
    kmhelpers apply index.yaml -o /output --show-progress

    \b
    # Plan: check paths and preview build without executing
    kmhelpers apply index.yaml -o /output --plan

    \b
    # Skip compression of intermediate files
    kmhelpers apply index.yaml -o /output --skip-compression

    \b
    # Resolve sample paths from a base directory
    kmhelpers apply index.yaml -o /output -b /data/samples

    \b
    # Set number of threads and minimizer size
    kmhelpers apply index.yaml -o /output -t 8 --minim-size 12

    """

    force = (ctx.obj or {}).get("yes", False)

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
        selected_ids = [id for entry in index_ids for id in entry.split(",") if id]
        selected_spans = _parse_spans(span)
        if not existing:
            existing = "fail"
        if not minim_size:
            minim_size = 10
    except Exception as e:
        pykmhelpers.core.log.Log.handle_exception(logger, e, f"Invalid argument.")
        raise click.ClickException(abort_msg)

    work_dir = os.path.realpath(work_dir or "build")

    if not registry:
        registry = work_dir
    else:
        registry = os.path.realpath(registry)

    if not bloom_dir:
        base_bloom_dir = os.path.join(work_dir, "kmindex_data")
    else:
        base_bloom_dir = os.path.realpath(bloom_dir)

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
        input_file_dir = os.path.basename(os.path.dirname(os.path.realpath(input_file)))
        index_data_folder = os.path.join(base_bloom_dir, input_file_dir)

        if os.path.isdir(index_data_folder) and not force:
            click.confirm(
                f"Bloom filter directory already exists at {index_data_folder}. Continue?",
                abort=True,
            )

        try:
            iops = ops.IndexOps(
                config=ops.IndexOpsConfig(
                    workdir=work_dir,
                    index_data_folder=index_data_folder,
                    registry_dir=os.path.join(work_dir, registry),
                    minimizer_length=int(minim_size),
                    sample_rootpath=base_path,
                    kmindex_threads=threads,
                    kmindex_skip_compression=skip_compression,
                    kmindex_build_from=reuse_from,
                    filter_names=selected_ids,
                    filter_spans=selected_spans,
                    on_existing=existing,
                    partition_count=partition_count,
                    limits=limits,
                    safety_margin=safety_margin,
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
