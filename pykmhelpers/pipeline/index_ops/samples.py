import json
import logging
import os
from typing import Optional

from pykmhelpers.core.log import Log
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import DbFields, IndexDefinition, Sample
from pykmhelpers.pipeline.index_ops.report import indent_prefix
from pykmhelpers.pipeline.index_ops.sources import DbCache

logger = logging.getLogger(__name__)


class SampleResolver:
    """Resolves the sample files of index definitions into a ``FofManager``.

    Sample files may be listed inline in the definition, or in a JSONL sample
    file (header line with an optional ``root_path``, then one
    ``{"name", "files"}`` record per line) referenced by ``sample_file``.
    """

    def __init__(
        self, sample_rootpath: Optional[str], check_files: bool, cache: DbCache
    ) -> None:
        self._rootpath = sample_rootpath
        self._check_files = check_files
        self._cache = cache
        self._enriched = set[int]()
        self._sample_files = dict[str, dict[str, list[str]]]()

    def build_fof(self, i: IndexDefinition) -> tuple[FofManager, list[str]]:
        """Return the fof of ``i`` and the issues of the samples that were skipped."""
        self._enrich_from_sample_file(i)
        fof = FofManager()
        issues: list[str] = []
        for s in i.samples.values():
            try:
                self._add_sample(fof, s)
            except Exception as e:
                msg = f"Error adding sample '{s.name or 'UNNAMED'}' to '{i.name}' | {e}"
                Log.handle_exception(
                    logger=logger,
                    e=e,
                    msg=f"{indent_prefix(logger)}{msg}",
                    level=logging.WARNING,
                )
                issues.append(msg)
        return fof, issues

    def _add_sample(self, fof: FofManager, s: Sample) -> None:
        if not s.name:
            raise ValueError("Empty name")
        if not s.files:
            raise ValueError("Empty file list")
        if s.name == "_":
            return
        # Relative paths are joined to the root again here, even when they
        # came from a sample file already joined to its own root.
        files = (
            [
                f if os.path.isabs(f) else os.path.join(self._rootpath, f)
                for f in s.files
            ]
            if self._rootpath
            else s.files
        )
        if self._check_files:
            for f in files:
                if not os.path.isfile(f):
                    raise FileNotFoundError(f"Sample file not found: {f}")
        fof.add_sample(files, s.name)

    def _enrich_from_sample_file(self, i: IndexDefinition) -> None:
        """Fill the file list of samples of ``i`` from its sample file, once per definition."""
        if not i.sample_file or id(i) in self._enriched:
            return
        self._enriched.add(id(i))

        source_dir = self._cache.source_dir(i.parent_db)
        path = (
            os.path.join(source_dir, i.sample_file)
            if source_dir and not os.path.isabs(i.sample_file)
            else i.sample_file
        )
        if not os.path.isfile(path):
            logger.warning(f"Sample file not found: {path}")
            return

        sample_files = self._read_sample_file(path)
        for sample in i.samples.values():
            if not sample.files:
                lookup = sample.get_link(DbFields.ORIGINAL_ID) or sample.name
                if lookup and lookup in sample_files:
                    sample.files = sample_files[lookup]

    def _read_sample_file(self, path: str) -> dict[str, list[str]]:
        """Parse a JSONL sample file once per path: sample name -> file paths."""
        if path in self._sample_files:
            return self._sample_files[path]

        sample_files: dict[str, list[str]] = {}
        with open(path) as f:
            header = json.loads(f.readline())
            root_path = self._rootpath or header.get("root_path", "")
            for line in f:
                data = json.loads(line)
                name = data.get("name")
                files = data.get("files", [])
                if name and files:
                    sample_files[name] = (
                        [os.path.join(root_path, fp) for fp in files]
                        if root_path
                        else files
                    )
        self._sample_files[path] = sample_files
        logger.debug(f"Loaded sample paths from {path}")
        return sample_files
