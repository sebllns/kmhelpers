"""Build a JSONL sample index from a directory scan or a plain-text sample list."""

import json
import logging
import os
import typing
from datetime import datetime, timezone

import yaml

from pykmhelpers.core.constants import DATA_EXT
from pykmhelpers.core.kmer import KmerCounter, KmerCountMode
from pykmhelpers.pipeline.index_db import IndexDefinitionTools

logger = logging.getLogger(__name__)


class SampleLister:
    """Scan directories or import a plain-text list to produce a JSONL sample index.

    Each output line is a JSON object with at least ``name`` and ``files`` keys.
    The first line is a header object carrying metadata (k-mer size, root path,
    assembly type, abundance minimum).  Existing output files are backed up as
    ``<output>.bak`` so an interrupted run can be resumed without re-scanning
    files already processed.

    Args:
        output_file:     Path to the JSONL file to write (created or overwritten).
        input_dir:       Root directory scanned recursively for sample files.
        input_list:      Plain-text file listing samples (``[id] file[,file] [count]``).
        kmer_size:       K-mer length passed to ntcard (default 25).
        is_assembled:    True for assembled sequences (distinct k-mer count),
                         False for raw reads (solid k-mer count).
        do_count:        Count k-mers with ntcard when no count is already known.
        do_grouping:     Group all files in a leaf directory under one sample ID.
        autorename:      Append ``_N`` suffix to duplicate IDs instead of skipping.
        ntcard_threads:  Thread count for ntcard (default 8).
    """

    def __init__(
        self,
        output_file: str,
        input_dir: str | None = None,
        input_list: str | None = None,
        kmer_size: int = 25,
        is_assembled: bool = True,
        do_count: bool = True,
        do_grouping: bool = True,
        autorename: bool = False,
        ntcard_threads: int = 8,
    ):
        self.output_file = output_file
        self.input_dir = input_dir
        self.input_list = input_list
        self.kmer_size = kmer_size
        self.is_assembled = is_assembled
        self.do_count = do_count
        self.do_grouping = do_grouping
        self.autorename = autorename
        self.ntcard_threads = ntcard_threads

        self._tools = IndexDefinitionTools()
        self._samples: set[str] = set()
        self._counter: KmerCounter | None = None
        self._count_mode = (
            KmerCountMode.DISTINCT if is_assembled else KmerCountMode.SOLID
        )

    def run(self) -> None:
        do_scan = self.input_dir is not None
        do_import = self.input_list is not None

        if self.input_dir and not os.path.isdir(self.input_dir):
            raise NotADirectoryError(
                f"Input directory does not exist: {self.input_dir}"
            )
        if self.input_dir:
            self.input_dir = os.path.realpath(self.input_dir)

        backup_file: str | None = None
        if os.path.exists(self.output_file):
            backup_file = str(self.output_file) + ".bak"
            os.replace(self.output_file, backup_file)
            logger.info(f"Backed up existing output file to {backup_file}")
        else:
            if self.input_dir is None and self.input_list is None:
                raise ValueError(
                    "--dir or --list is required when creating a new sample list"
                )

        if self.do_count:
            self._counter = KmerCounter(
                k=self.kmer_size, threadCount=self.ntcard_threads
            )

        backup_parsed = False
        with open(self.output_file, "w") as out:
            self._out = out

            if not backup_file:
                root_path = self.input_dir or (
                    os.path.dirname(os.path.realpath(self.input_list))
                    if self.input_list
                    else None
                )
                self._out.write(
                    self._new_header(
                        root_path,
                        self.kmer_size,
                        self.is_assembled,
                        self._tools.get_abundance_min(self.is_assembled),
                    )
                )
            else:
                self.input_dir, self.kmer_size, backup_parsed = self._process_backup(
                    backup_file
                )
                root_path = self.input_dir

            if self.input_list is not None:
                if self.input_list.endswith((".yaml", ".yml")):
                    self._import_yaml_list(
                        self.input_list, self._process_sample, root_path
                    )
                else:
                    self._import_plain_text_list(
                        self.input_list, self._process_sample, root_path
                    )

            scan_dir = self.input_dir
            if scan_dir is not None and (do_scan or (backup_parsed and not do_import)):
                self._process_samples(scan_dir, DATA_EXT, self._process_sample)

            if not do_scan and not do_import and not backup_parsed:
                logger.warning(
                    "No input directory provided and no existing sample list found: nothing to do."
                )
            else:
                logger.info(
                    f"Listed {len(self._samples)} samples -> {self.output_file}"
                )

    def _import_yaml_list(
        self,
        input_list,
        process_callback: typing.Callable[[str, list[str], int], None],
        root_path: str | None = None,
    ):
        with open(input_list) as f:
            data = yaml.safe_load(f)

        header = {k: v for k, v in data.items() if k != "samples"}

        self._out.write(json.dumps(header) + "\n")
        for name, attrs in data["samples"].items():
            files = (
                [
                    f if os.path.isabs(f) else os.path.join(root_path, f)
                    for f in attrs.get("files", [])
                ]
                if root_path
                else attrs.get("files", [])
            )
            process_callback(name, files, attrs.get("kmer_count", 0))

    def _process_sample(
        self, sample_id: str, files: list[str], kmer_count: int
    ) -> None:
        try:
            assert sample_id, "Sample ID null or empty"
            assert files, "Sample file list null or empty"

            if sample_id in self._samples:
                if self.autorename:
                    n = 1
                    while f"{sample_id}_{n}" in self._samples:
                        n += 1
                    sample_id = f"{sample_id}_{n}"
                    logger.info(f"Duplicate sample ID renamed to {sample_id}")
                else:
                    logger.info(f"Duplicate sample ID: {sample_id}, skipping {files}")
                    return
            self._samples.add(sample_id)
            entry: dict = {"name": sample_id, "files": files}

            if self.do_count and kmer_count <= 0:
                kmer_count = self._count_sample(sample_id, files)

            if kmer_count > 0:
                entry["kmer_count"] = kmer_count

            self._out.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Could not write entry for '{sample_id or '<NONE>'}': {e}")

    def _count_sample(self, sample_id: str, files: list[str]) -> int:
        if self._counter is None:
            return 0
        try:
            kmer_count = self._counter.count_files(
                files, mode=self._count_mode, verbose=logger.isEnabledFor(logging.DEBUG)
            )
            logger.info(f"{sample_id}:{kmer_count}")
            return kmer_count
        except Exception as e:
            logger.warning(f"Warning: could not count k-mers for {sample_id}: {e}")
            return 0

    def _import_plain_text_list(
        self,
        filename: str,
        process_callback: typing.Callable[[str, list[str], int], None],
        root_path: str | None = None,
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
                    sample_id = self._tools.clean_sample_id(
                        os.path.splitext(os.path.basename(files_str.split(",")[0]))[0]
                    )
                else:
                    sample_id = self._tools.clean_sample_id(parts[0])
                    files_str = " ".join(parts[1:])

                files = [f.strip().strip('"').strip("'") for f in files_str.split(",")]
                if root_path:
                    files = [
                        f if os.path.isabs(f) else os.path.join(root_path, f)
                        for f in files
                    ]
                if files:
                    process_callback(sample_id, files, kmer_count)

    def _process_samples(
        self,
        root: str,
        extensions: tuple[str, ...],
        process_callback: typing.Callable[[str, list[str], int], None],
    ) -> None:
        """Walk root and call process_callback(sample_id, files, kmer_count) for each sample.

        do_grouping=True  -> group files by leaf folder name
        do_grouping=False -> treat each file as its own sample
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

            if self.do_grouping:
                sample_id = self._tools.clean_sample_id(os.path.basename(dirpath))
                process_callback(sample_id, data_files, 0)
            else:
                for filepath in data_files:
                    fname = os.path.basename(filepath)
                    base = next(
                        (
                            fname[: -len(ext)]
                            for ext in extensions
                            if fname.endswith(ext)
                        ),
                        fname,
                    )
                    sample_id = self._tools.clean_sample_id(base)
                    process_callback(sample_id, [filepath], 0)

    def _process_backup(self, backup_file: str) -> tuple:
        input_dir = self.input_dir
        kmer_size = self.kmer_size

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
                input_dir = first_entry.get("root_path") or input_dir
                is_assembled = first_entry.get("assembled", self.is_assembled)
                first_entry["k"] = kmer_size
                first_entry["root_path"] = input_dir
                first_entry["assembled"] = is_assembled
                first_entry.setdefault("description", "Generated by kmhelpers list")
                first_entry.setdefault(
                    "date",
                    datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
                )
                self._out.write(json.dumps(first_entry) + "\n")

                if "name" in first_entry:
                    entry = first_entry
                    self._samples.add(entry["name"])
                    if self.do_count and "kmer_count" not in entry:
                        entry["kmer_count"] = self._count_sample(
                            entry["name"], entry.get("files", [])
                        )
                    self._out.write(json.dumps(entry) + "\n")

                for line in src:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Could not parse existing entry: {line.strip()}"
                        )
                        continue
                    if "name" in entry:
                        self._process_sample(
                            entry.get("name"),
                            entry.get("files"),
                            entry.get("kmer_count", 0),
                        )

        return input_dir, kmer_size, parsed

    @staticmethod
    def _new_header(input_dir, kmer_size, is_assembled, abundance_min) -> str:
        header = {
            "description": "Generated by kmhelpers list",
            "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f"),
            "root_path": input_dir,
            "k": kmer_size,
            "assembled": is_assembled,
            "abundance_min": abundance_min,
        }
        return json.dumps(header) + "\n"
