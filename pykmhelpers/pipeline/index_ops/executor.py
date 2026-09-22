import logging
import os
import shutil

from pykmhelpers.core.log import Log
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import IndexDefinition
from pykmhelpers.pipeline.index_ops.progress import progress_for
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams
from pykmhelpers.pipeline.index_ops.types import ApplyMode, IndexOpsConfig

logger = logging.getLogger(__name__)


def validate_definition(i: IndexDefinition) -> None:
    if not i.name:
        raise ValueError("IndexDefinition is missing required 'name' field")
    if not i.bf_size > 0:
        raise ValueError(
            f"IndexDefinition {i.name} is missing required 'bf_size' field"
        )


class IndexExecutor:
    """Runs kmindex build, merge and cleanup commands against one registry.

    In non-executing modes (dry-run, plan), commands are only generated and
    recorded into the script; registry checks and file deletions are skipped.
    """

    def __init__(
        self,
        builder: IndexBuilder,
        mode: ApplyMode,
        config: IndexOpsConfig,
        script: ScriptRecorder,
    ) -> None:
        self._builder = builder
        self._mode = mode
        self._config = config
        self._script = script
        self._claimed = set[str]()

    @property
    def executes(self) -> bool:
        return self._mode.executes

    def has_index(self, name: str) -> bool:
        return self._builder.index.has_index(name)

    def claim(self, name: str) -> bool:
        """Reserve ``name`` for a build in this run. False if already claimed or built."""
        self._builder.index.load_json()
        if name in self._claimed or self._builder.has_subindex(name):
            return False
        self._claimed.add(name)
        return True

    def build(
        self, i: IndexDefinition, fof: FofManager, params: BuildParams
    ) -> dict | None:
        """Build index ``i`` from ``fof``, split into chunks if ``params`` requires it."""
        assert i.name
        if params.chunk_size is None:
            return self._build_one(i.name, fof, i, params)
        return self._build_chunked(i, fof, params)

    def missing_parts(self, parts: list[str]) -> list[str]:
        """Parts not present in the registry (always empty when not executing)."""
        self._builder.index.load_json()
        if not self.executes:
            return []
        return [name for name in parts if not self._builder.index.has_index(name)]

    def merge(self, target: str, parts: list[str], threads: int) -> dict | None:
        """Merge ``parts`` into ``target``. Call ``finalize_merge`` afterwards."""
        result: dict | None = self._builder.merge(
            target, parts, delete_old=False, dry_run=not self.executes, threads=threads
        )
        if result and "command" in result:
            label = f"merge {','.join(parts)} -> {target}"
            self._script.add(result["command"], label)
        return result

    def finalize_merge(self, target: str, parts: list[str]) -> None:
        """Check that ``target`` exists and, if its structure is valid, delete ``parts``.

        When not executing, the deletion is scripted instead; the script stops
        before it if the merge fails.
        """
        if not self.executes:
            # kmindex merge already unregisters the parts: only their data is left
            for part in parts:
                path = os.path.join(self._config.index_data_folder, part)
                self._script.add(
                    f'rm -rf "$(realpath -m {path})" "{path}"', f"cleanup {part}"
                )
            return
        self._verify(target)
        if self._builder.index.get_index(target).check_structure():
            for part in parts:
                self.delete_segment(part)

    def delete_segment(self, segment: str) -> None:
        """Unregister ``segment`` and delete its data directory."""
        logger.info(f"Delete {segment}...")
        try:
            self._builder.index.remove_index(
                segment, delete_files=False, skip_unregistered=True
            )
        except Exception as e:
            Log.handle_exception(
                logger, e, f"Failed to remove {segment} from registry", logging.WARNING
            )

        index_path = os.path.join(self._config.index_data_folder, segment)
        shutil.rmtree(os.path.realpath(index_path), ignore_errors=True)
        try:
            if os.path.islink(index_path):
                os.unlink(index_path)
        except Exception as e:
            Log.handle_exception(
                logger, e, f"Error deleting link {index_path}", logging.WARNING
            )
        if os.path.exists(index_path):
            logger.warning(
                f"Could not remove dir {index_path}, please remove it manually."
            )

    def _build_one(
        self, name: str, fof: FofManager, i: IndexDefinition, params: BuildParams
    ) -> dict | None:
        """Build one physical sub-index ``name`` from ``fof`` with the parameters of ``i``."""
        if self._mode is ApplyMode.APPLY:
            logger.info(f"  └── Building '{name}'...")

        with progress_for(self._mode, name) as progress:
            result = self._builder.create_subindex(
                name=name,
                samples=fof,
                abundance_min=i.abundance_min,
                bloom_size=i.bf_size,
                n_partitions=params.partitions,
                n_threads=params.threads,
                auto_check=True,
                compress_intermediate=not self._config.kmindex_skip_compression,
                minim_size=self._config.minimizer_length,
                dry_run=not self.executes,
                kmer_size=i.kmer_size,
                on_existing=self._config.on_existing,
                progress=progress.handler,
            )
            if result and "command" in result:
                self._script.add(result["command"], f"build {name}")

        if self.executes:
            self._verify(name)
        return result

    def _build_chunked(
        self, i: IndexDefinition, fof: FofManager, params: BuildParams
    ) -> dict | None:
        """Build ``i`` as transient ``{name}__chunk{n}`` sub-indexes, then merge them into ``i.name``."""
        assert i.name and params.chunk_size
        size = params.chunk_size
        items = list(fof.samples.items())
        chunks = [items[n : n + size] for n in range(0, len(items), size)]
        chunk_names = [f"{i.name}__chunk{n}" for n in range(len(chunks))]

        logger.info(
            f"  └── Splitting '{i.name}' into {len(chunks)} chunks of up to "
            f"{size} samples (open-files limit)"
        )
        for chunk_name, chunk_items in zip(chunk_names, chunks):
            self._build_one(
                chunk_name, FofManager(samples=dict(chunk_items)), i, params
            )

        result = self.merge(i.name, chunk_names, params.threads)
        self.finalize_merge(i.name, chunk_names)
        return result

    def _verify(self, name: str) -> None:
        self._builder.index.load_json()
        if not self._builder.has_subindex(name):
            raise RuntimeError(f"Could not find index '{name}'")
