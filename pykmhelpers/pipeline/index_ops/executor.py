import logging
import os
import shlex
import shutil
from dataclasses import replace

from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.core.kmindex_paths import chunk_problems
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import Toolbox, summarize_names
from pykmhelpers.operations.builder import IndexBuilder
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import IndexDefinition
from pykmhelpers.pipeline.index_ops.merging import (
    MergeLimits,
    footprint,
    max_inputs,
    merge_threads,
    merge_tree,
    repartition_bytes,
)
from pykmhelpers.pipeline.index_ops.progress import progress_for
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams
from pykmhelpers.pipeline.index_ops.types import ApplyMode, IndexOpsConfig

logger = logging.getLogger(__name__)

MERGE_REGISTRIES = "merge_registries"


def _size(n_bytes: float) -> str:
    return str(ByteCounter.auto(int(n_bytes), SizeFormat.BYTE))


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

    def align_with(self, target: str, params: BuildParams) -> BuildParams:
        """Match ``params`` to an already registered ``target``.

        kmindex refuses to merge indexes whose partition count or minimizer
        size differ, so a part joining an existing shard must reuse them.
        """
        if not self._builder.index.has_index(target):
            return params

        registered = self._builder.index.get_index(target)
        aligned = params
        if registered.nb_partitions and registered.nb_partitions != params.partitions:
            logger.warning(
                f"'{target}' is registered with {registered.nb_partitions} partitions, "
                f"not {params.partitions}: building with the registered count"
            )
            aligned = replace(aligned, partitions=registered.nb_partitions)
        if registered.minim_size and registered.minim_size != params.minim_size:
            logger.warning(
                f"'{target}' is registered with minimizer size "
                f"{registered.minim_size}, not {params.minim_size}: building with "
                f"the registered size"
            )
            aligned = replace(aligned, minim_size=registered.minim_size)
        return aligned

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
            label = f"merge {summarize_names(parts)} -> {target}"
            self._script.add(result["command"], label)
        return result

    def finalize_merge(self, target: str, parts: list[str]) -> None:
        """Check that ``target`` exists and, if its structure is valid, delete ``parts``.

        When not executing, the deletion is scripted instead; the script stops
        before it if the merge fails.
        """
        if not self.executes:
            # kmindex merge already unregisters the parts: only their data is
            # left. One loop rather than a line per part: a chunked build has
            # as many of them as it has chunks.
            paths = " ".join(
                shlex.quote(os.path.join(self._config.index_data_folder, part))
                for part in parts
            )
            self._script.add(
                # cd -P resolves a symlinked part portably (no GNU realpath -m)
                f"for d in {paths}; do "
                'if p=$(cd -P "$d" 2>/dev/null && pwd); then rm -rf "$p"; fi; '
                'rm -rf "$d"; done',
                f"cleanup {summarize_names(parts)}",
            )
            return
        self._verify(target)
        if self._builder.index.get_index(target).check_structure():
            logger.info(f"Deleting merged {summarize_names(parts)}...")
            for part in parts:
                self.delete_segment(part)

    def delete_segment(self, segment: str) -> None:
        """Unregister ``segment`` and delete its data directory."""
        logger.debug(f"Delete {segment}...")
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
        self,
        name: str,
        fof: FofManager,
        i: IndexDefinition,
        params: BuildParams,
        register: bool = True,
    ) -> dict | None:
        """Build one physical sub-index ``name`` from ``fof`` with the parameters of ``i``.

        ``register=False`` builds an unregistered kmtricks run (a chunk).
        """
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
                minim_size=params.minim_size,
                dry_run=not self.executes,
                kmer_size=i.kmer_size,
                on_existing=self._config.on_existing,
                progress=progress.handler,
                register=register,
            )
            if result and "command" in result:
                self._script.add(result["command"], f"build {name}")

        if self.executes and register:
            self._verify(name)
        return result

    def _build_chunked(
        self, i: IndexDefinition, fof: FofManager, params: BuildParams
    ) -> dict | None:
        """Build ``i`` as unregistered ``{name}_chunk{n}`` runs, then merge them into ``i.name``."""
        assert i.name and params.chunk_size
        size = params.chunk_size
        items = list(fof.samples.items())
        chunks = [items[n : n + size] for n in range(0, len(items), size)]
        chunk_names = [f"{i.name}_chunk{n}" for n in range(len(chunks))]

        logger.info(
            f"  └── Splitting '{i.name}' into {len(chunks)} chunks of up to "
            f"{size} samples (open-files limit)"
        )
        for chunk_name, chunk_items in zip(chunk_names, chunks):
            self._build_one(
                chunk_name,
                FofManager(samples=dict(chunk_items)),
                i,
                params,
                register=False,
            )

        samples = {name: len(items) for name, items in zip(chunk_names, chunks)}
        return self.merge_chunks(i, samples, params)

    def merge_chunks(
        self, i: IndexDefinition, chunk_samples: dict[str, int], params: BuildParams
    ) -> dict | None:
        """Merge the unregistered chunk runs of ``i`` and register the result.

        Recorded in the merge script of the current group, run after its builds:

        1. check that every chunk run is complete (else stop before registering);
        2. split the chunks into merges of at most ``k`` inputs, ``k`` set by the
           resource limits (``max_inputs``), in a balanced tree;
        3. run each merge in a throwaway registry holding only its inputs;
        4. register ``i.name`` in the main registry;
        5. delete the chunk runs, the intermediate merges and the registries.
        """
        assert i.name
        target = i.name
        data = self._config.index_data_folder
        main_registry = self._builder.index.root_path
        registries = os.path.join(main_registry, MERGE_REGISTRIES, target)
        partitions = params.partitions
        threads = merge_threads(params.threads, partitions)
        chunks = list(chunk_samples)
        run_dirs = {name: os.path.join(data, name) for name in chunks}

        group = self._script.current or target
        self._script.select(ScriptRecorder.merge_group(group))

        # 1. every chunk must be complete before anything is registered
        chunks_tsv = self._write_tsv(f"{target}.chunks.tsv", run_dirs)
        if self.executes:
            incomplete = {
                name: problems
                for name, path in run_dirs.items()
                if (problems := chunk_problems(path, partitions))
            }
            if incomplete:
                details = "; ".join(
                    f"{n}: {', '.join(p)}" for n, p in incomplete.items()
                )
                raise RuntimeError(
                    f"{len(incomplete)} chunk(s) of '{target}' are incomplete, "
                    f"not merging: {details}"
                )
        self._script.add(
            self._check_chunks_cmd(chunks_tsv, partitions),
            f"check {summarize_names(chunks)}",
        )

        # 2. merge tree within the resource limits
        limits = MergeLimits.resolve(self._config.limits, self._config.safety_margin)
        k, binding = max_inputs(limits, partitions, params.minim_size, threads)
        steps = merge_tree(target, chunks, k)
        logger.info(
            f"  └── Merging {len(chunks)} chunks into '{target}': "
            f"{len(steps)} merge(s), at most {k} inputs each ({binding} limit), "
            f"{threads} thread(s)"
        )

        samples = dict(chunk_samples)
        wrapper = KmindexWrapper(dry_run=not self.executes)
        result: dict | None = None
        for step in steps:
            samples[step.name] = sum(samples[n] for n in step.inputs)
            fp = footprint(
                [samples[n] for n in step.inputs],
                len(step.inputs),
                partitions,
                params.minim_size,
                i.bf_size,
                threads,
            )
            note = (
                ", more than the RAM limit: relies on page-cache reclaim"
                if fp["mapped"] > limits.ram
                else ""
            )
            logger.info(
                f"      {step.name}: {len(step.inputs)} inputs, "
                f"anonymous {_size(fp['anon'])}, mapped inputs {_size(fp['mapped'])}{note}"
            )

            # 3. a registry of its own, holding only this merge's inputs
            registry = os.path.join(registries, step.name)
            inputs = {n: run_dirs.get(n) or os.path.join(data, n) for n in step.inputs}
            tsv = self._write_tsv(f"{step.name}.register.tsv", inputs)
            self._reset(registry)
            r = wrapper.register(registry, from_file=tsv)
            self._script.add(r["command"], f"register {summarize_names(step.inputs)}")
            result = wrapper.merge(
                input_registry=registry if self.executes else main_registry,
                new_name=step.name,
                new_path=os.path.join(data, step.name),
                to_merge=step.inputs,
                threads=threads,
            )
            if not self.executes:
                # The step registry only exists once the script registered the
                # inputs: the command was built against the main registry.
                planned = Toolbox.get_canonical_path(main_registry)
                command = result["command"]
                assert f"--index {planned} " in command, command
                result["command"] = command.replace(
                    f"--index {planned} ",
                    f"--index {Toolbox.get_canonical_path(registry)} ",
                    1,
                )
            self._script.add(
                result["command"],
                f"merge {summarize_names(step.inputs)} -> {step.name}",
            )
            intermediates = [n for n in step.inputs if n not in run_dirs]
            self._remove(
                [registry] + [os.path.join(data, n) for n in intermediates],
                f"cleanup {step.name} registry",
            )

        # 4. publish the merged index in the main registry
        r = wrapper.register(
            main_registry, name=target, index_path=os.path.join(data, target)
        )
        self._script.add(r["command"], f"register {target}")
        if self.executes:
            self._builder.index.load_json()
            self._verify(target)
            if not self._builder.index.get_index(target).check_structure():
                raise RuntimeError(f"Merged index '{target}' has an invalid structure")

        # 5. chunks and throwaway registries are no longer needed
        self._remove(list(run_dirs.values()), f"cleanup {summarize_names(chunks)}")
        self._remove([registries], f"cleanup {MERGE_REGISTRIES}/{target}")
        parent = os.path.dirname(registries)
        if self.executes:
            try:
                os.rmdir(parent)
            except OSError:
                pass  # other targets still have registries there
        else:
            self._script.add(
                f"rmdir --ignore-fail-on-non-empty {shlex.quote(parent)}",
                f"cleanup {MERGE_REGISTRIES}",
            )
        self._script.select(group)
        return result

    def registered_partitions(self, names: list[str]) -> int:
        """Partition count of the first of ``names`` found in the registry (0 if none)."""
        self._builder.index.load_json()
        for name in names:
            if self._builder.index.has_index(name):
                n = self._builder.index.get_index(name).nb_partitions
                if n:
                    return n
        return 0

    def registered_count(self, extra: list[str]) -> int:
        """Entries of the main registry once ``extra`` are registered too."""
        self._builder.index.load_json()
        return len(set(self._builder.index.list_indices()) | set(extra))

    def check_merge_budget(
        self, target: str, n_registered: int, minim_size: int
    ) -> None:
        """Check the anonymous memory of a merge run in the main registry.

        ``kmindex merge`` loads the repartition table of every registered
        sub-index: ``n_registered * 2 * 4^m`` bytes that must fit in RAM.
        Raises when executing, logs an error when planning.
        """
        limits = MergeLimits.resolve(self._config.limits, self._config.safety_margin)
        anon = n_registered * repartition_bytes(minim_size)
        msg = (
            f"Merging '{target}' loads {n_registered} registered sub-indexes: "
            f"{_size(anon)} of anonymous memory"
        )
        if anon <= limits.ram:
            logger.info(f"  └── {msg}")
            return
        msg += f", more than the RAM limit ({_size(limits.ram)})"
        if self.executes:
            raise RuntimeError(msg)
        logger.error(msg)

    def _write_tsv(self, file_name: str, entries: dict[str, str]) -> str:
        """Write ``name<TAB>path`` lines to the assets folder; return the file path."""
        path = os.path.join(self._builder.assets_folder, file_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.writelines(f"{name}\t{p}\n" for name, p in entries.items())
        return path

    @staticmethod
    def _check_chunks_cmd(chunks_tsv: str, partitions: int) -> str:
        """Shell loop stopping the script when a chunk run is incomplete.

        Same test as ``chunk_problems``: kmtricks writes ``run_infos.txt`` only
        after its last stage; all ``partitions`` matrices must be non-empty and
        of one size.
        """
        tsv = shlex.quote(chunks_tsv)
        return (
            "bad=0; while IFS=$'\\t' read -r name dir; do "
            'n=$(ls "$dir"/matrices/matrix_*.cmbf 2>/dev/null | wc -l); '
            'sizes=$(stat -c %s "$dir"/matrices/matrix_*.cmbf 2>/dev/null | sort -u); '
            'if [ ! -s "$dir/run_infos.txt" ] || [ ! -f "$dir/kmtricks.fof" ] '
            '|| [ ! -f "$dir/options.txt" ] '
            f'|| [ "$n" -ne {partitions} ] || [ "$(echo "$sizes" | wc -l)" -ne 1 ] '
            '|| [ "$sizes" = 0 ]; then '
            'echo "incomplete chunk: $name ($dir)" >&2; bad=$((bad + 1)); fi; '
            f"done < {tsv}; "
            'if [ "$bad" -gt 0 ]; then echo "$bad incomplete chunk(s): not merging" >&2; '
            "exit 1; fi"
        )

    def _reset(self, registry: str) -> None:
        """Start a merge registry empty (a previous attempt may have left one)."""
        if self.executes:
            shutil.rmtree(registry, ignore_errors=True)
        self._script.add(f"rm -rf {shlex.quote(registry)}", "reset merge registry")

    def _remove(self, paths: list[str], label: str) -> None:
        """Delete ``paths`` (resolving symlinked directories), or script it."""
        if not paths:
            return
        if self.executes:
            for p in paths:
                shutil.rmtree(os.path.realpath(p), ignore_errors=True)
                if os.path.islink(p):
                    os.unlink(p)
                shutil.rmtree(p, ignore_errors=True)
            return
        quoted = " ".join(shlex.quote(p) for p in paths)
        self._script.add(
            f"for d in {quoted}; do "
            'if p=$(cd -P "$d" 2>/dev/null && pwd); then rm -rf "$p"; fi; '
            'rm -rf "$d"; done',
            label,
        )

    def _verify(self, name: str) -> None:
        self._builder.index.load_json()
        if not self._builder.has_subindex(name):
            raise RuntimeError(f"Could not find index '{name}'")
