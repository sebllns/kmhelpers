"""Recursively list samples from a directory and output a JSONL file."""

import json
import logging
import os
import platform
import sys
import typing
from datetime import datetime, timezone

import click

import pykmhelpers
from pykmhelpers.core.constants import DATA_EXT
from pykmhelpers.core.kmer import KmerCounter, KmerCountMode
from pykmhelpers.pipeline.index_db import IndexDefinitionTools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample discovery helpers
# ---------------------------------------------------------------------------


def _import_plain_text_list(
    filename: str,
    process_callback: typing.Callable[[str, list[str], int], None],
    tools: IndexDefinitionTools,
) -> None:
    # Plain text: [sample_id] file_1[,file_2,...] [kmer_count]
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            kmer_count = 0
            try:
                kmer_count = int(parts[-1])
                parts = parts[:-1]
            except ValueError:
                pass

            if not parts:
                logger.warning(
                    f"Invalid line format: {line}. "
                    "Expected: [sample_id] file_1[,file_2,...] [kmer_count]"
                )
                continue

            if len(parts) == 1:
                files_str = parts[0]
                sample_id = tools.clean_sample_id(
                    os.path.splitext(os.path.basename(files_str.split(",")[0]))[0]
                )
            else:
                sample_id = tools.clean_sample_id(parts[0])
                files_str = " ".join(parts[1:])

            files = [f.strip().strip('"').strip("'") for f in files_str.split(",")]
            if files:
                process_callback(sample_id, files, kmer_count)


def _process_samples(
    root: str,
    extensions: tuple[str, ...],
    with_grouping: bool,
    process_callback: typing.Callable[[str, list[str], int], None],
    tools: IndexDefinitionTools,
) -> None:
    """Walk root and call process_callback(sample_id, files) for each sample.

    with_grouping=True  -> group files by leaf folder name
    with_grouping=False -> treat each file as its own sample
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        data_files = [
            os.path.relpath(os.path.join(dirpath, fname), root)
            for fname in sorted(filenames)
            if any(fname.endswith(ext) for ext in extensions)
        ]

        if not data_files:
            continue

        if with_grouping:
            sample_id = tools.clean_sample_id(os.path.basename(dirpath))
            process_callback(sample_id, data_files, 0)
        else:
            for filepath in data_files:
                fname = os.path.basename(filepath)
                base = next(
                    (fname[: -len(ext)] for ext in extensions if fname.endswith(ext)),
                    fname,
                )
                sample_id = tools.clean_sample_id(base)
                process_callback(sample_id, [filepath], 0)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@click.command(name="list")
@click.argument(
    "output_file",
    nargs=1,
    required=True,
    type=click.Path(dir_okay=False),
    # help="Output JSONL file path",
)
@click.option(
    "--input",
    "-i",
    "input_dir",
    required=False,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Input directory to scan recursively for sample files",
)
@click.option(
    "--list",
    "-l",
    "input_list",
    required=False,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Import input list in plain text format",
)
@click.option(
    "--kmer-size",
    "-k",
    type=int,
    default=25,
    show_default=True,
    help="K-mer size used for counting",
)
@click.option(
    "--data-type",
    "-t",
    "data_type",
    type=click.Choice(["a", "assembled", "u", "unassembled"], case_sensitive=False),
    default="a",
    show_default=True,
    help="Data type: a/assembled (default) or u/unassembled (raw reads)",
)
@click.option(
    "--no-count",
    "no_count",
    is_flag=True,
    default=False,
    help="Count k-mers for each sample using ntcard",
)
@click.option(
    "--no-grouping",
    "no_grouping",
    is_flag=True,
    default=False,
    help="Disable grouping by leaf folder; each file becomes its own sample",
)
@click.option(
    "--autorename",
    "-r",
    is_flag=True,
    default=False,
    help="Rename duplicate sample IDs by appending a numeric suffix instead of skipping",
)
@click.option(
    "--ntcard-threads",
    "--ntt",
    "ntcard_threads",
    type=int,
    default=8,
    help="⚙️  Number of threads used by ntcard for k-mer counting (default: 8)",
)
@click.option(
    "--ntcard-value",
    "--ntv",
    "ntcard_value",
    default="F0",
    help="⚙️   Value ID to extract from ntcard output (default: 'F0')",
)
def list_samples(
    input_dir,
    input_list,
    output_file,
    kmer_size,
    data_type,
    no_count,
    no_grouping,
    autorename,
    ntcard_threads,
    ntcard_value,
):
    """Recursively list samples from a directory and output a JSONL file.

    By default, files are grouped by leaf folder: each leaf directory
    becomes one sample whose ID is the folder name. Use --no-grouping to
    treat every file independently.

    When --count is used, each completed k-mer count is saved to a cache
    file so an interrupted run can resume without recounting already-finished
    samples. The cache is deleted automatically on successful completion.
    """

    samples = set[str]()

    counter = None
    do_count = not no_count
    do_grouping = not no_grouping
    do_scan = input_dir is not None
    do_import = input_list is not None
    is_assembled = data_type.lower() in ("a", "assembled")

    tools = IndexDefinitionTools()

    # TODO make it dynamic due to backup file system
    count_mode = KmerCountMode.DISTINCT if is_assembled else KmerCountMode.SOLID

    if do_count:
        try:
            counter = KmerCounter(k=kmer_size, threadCount=ntcard_threads)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))

    def count_sample(sample_id: str, files: list[str]) -> int:
        if counter is None:
            return 0
        try:
            kmer_count = counter.count_files(files, mode=count_mode)
            logger.info(f"{sample_id}:{kmer_count}")
            return kmer_count
        except Exception as e:
            logger.warning(f"Warning: could not count k-mers for {sample_id}: {e}")
            return 0

    backup_file: str | None = None

    if input_dir:
        if not os.path.isdir(input_dir):
            raise click.UsageError(f"Input directory does not exist: {input_dir}")
        input_dir = os.path.realpath(input_dir)

    if os.path.exists(output_file):
        backup_file = str(output_file) + ".bak"
        os.replace(output_file, backup_file)
        logger.info(f"Backed up existing output file to {backup_file}")
    else:
        if input_dir is None and input_list is None:
            raise click.UsageError(
                "--input or --list is required when creating a new sample list"
            )

    backup_parsed = False
    with open(output_file, "w") as out:

        def process_sample(sample_id: str, files: list[str], kmer_count):
            try:
                assert sample_id, "Sample ID null or empty"
                assert files, "Sample file list null or empty"

                if sample_id in samples:
                    if autorename:
                        n = 1
                        while f"{sample_id}_{n}" in samples:
                            n += 1
                        sample_id = f"{sample_id}_{n}"
                        logger.info(f"Duplicate sample ID renamed to {sample_id}")
                    else:
                        logger.info(
                            f"Duplicate sample ID: {sample_id}, skipping {files}"
                        )
                        return
                samples.add(sample_id)
                entry: dict = {"name": sample_id, "files": files}

                if do_count and kmer_count <= 0:
                    kmer_count = count_sample(sample_id, files)

                if kmer_count > 0:
                    entry["kmer_count"] = kmer_count

                out.write(json.dumps(entry) + "\n")
            except Exception as e:
                logger.warning(
                    f"Could not write entry for '{sample_id or '<NONE>'}': {e}"
                )

        if not backup_file:
            out.write(
                _new_header(
                    input_dir,
                    kmer_size,
                    is_assembled,
                    tools.get_abundance_min(is_assembled),
                )
            )
        else:
            input_dir, kmer_size, backup_parsed = _process_backup(
                input_dir,
                kmer_size,
                is_assembled,
                samples,
                do_count,
                count_sample,
                backup_file,
                out,
                process_sample,
            )

        if do_import:
            _import_plain_text_list(input_list, process_sample, tools)

        if do_scan:
            _process_samples(input_dir, DATA_EXT, do_grouping, process_sample, tools)

        if not do_scan and not do_import and not backup_parsed:
            logger.warning(
                "No input directory provided and no existing sample list found: nothing to do."
            )
        else:
            total = len(samples)
            logger.info(f"Listed {total} samples -> {output_file}")


def _process_backup(
    input_dir,
    kmer_size,
    is_assembled,
    samples,
    do_count,
    count_sample,
    backup_file,
    out,
    process_sample,
):
    with open(backup_file) as src:
        first_line = src.readline()
        first_entry = {}
        try:
            first_entry = json.loads(first_line)
            parsed = True
        except json.JSONDecodeError:
            logger.warning("Could not parse existing header")
            parsed = False

        if parsed:
            kmer_size = first_entry.get("k", kmer_size)
            input_dir = (
                first_entry.get("root_path") or input_dir or os.path.realpath(".")
            )
            is_assembled = first_entry.get("assembled", is_assembled)
            first_entry["k"] = kmer_size
            first_entry["root_path"] = input_dir
            first_entry["assembled"] = is_assembled
            first_entry.setdefault("description", "Generated by kmhelpers list")
            first_entry.setdefault(
                "date",
                datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
            )
            out.write(json.dumps(first_entry) + "\n")

            if "name" in first_entry:
                entry = first_entry
                samples.add(entry["name"])
                if do_count and "kmer_count" not in entry:
                    entry["kmer_count"] = count_sample(
                        entry["name"], entry.get("files", [])
                    )
                out.write(json.dumps(entry) + "\n")

            for line in src:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse existing entry: {line.strip()}")
                    continue
                if "name" in entry:
                    process_sample(
                        entry.get("name"),
                        entry.get("files"),
                        entry.get("kmer_count", 0),
                    )

    return input_dir, kmer_size, parsed


def _new_header(input_dir, kmer_size, is_assembled, abundance_min):
    header = {
        "description": "Generated by kmhelpers list",
        "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
        "root_path": input_dir,
        "k": kmer_size,
        "assembled": is_assembled,
        "abundance_min": abundance_min,
    }
    header_line = json.dumps(header) + "\n"
    return header_line
