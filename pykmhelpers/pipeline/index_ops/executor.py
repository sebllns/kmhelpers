import datetime
import logging
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import replace

from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.core.kmindex_paths import chunk_problems
from pykmhelpers.core.utils import summarize_names
from pykmhelpers.operations.builder import IndexBuilder, backup_name
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_db import IndexDefinition
from pykmhelpers.pipeline.index_ops.merging import (
    MergeLimits,
    footprint,
    max_inputs,
    merge_threads,
    merge_tree,
)
from pykmhelpers.pipeline.index_ops.paths import BuildPaths
from pykmhelpers.pipeline.index_ops.progress import progress_for
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams
from pykmhelpers.pipeline.index_ops.types import ApplyMode, IndexOpsConfig

logger = logging.getLogger(__name__)


def _size(n_bytes: float) -> str:
    return str(ByteCounter.auto(int(n_bytes), SizeFormat.BYTE))


def _q(path: str) -> str:
    return shlex.quote(path)


def validate_definition(i: IndexDefinition) -> None:
    if not i.name:
        raise ValueError("IndexDefinition is missing required 'name' field")
    if not i.bf_size > 0:
        raise ValueError(
            f"IndexDefinition {i.name} is missing required 'bf_size' field"
        )


class IndexExecutor:
    """Builds kmtricks runs and publishes them as indexes of one registry.

    Every index is built as unregistered kmtricks runs in ``work/<session>/``
    (one, or several chunks), then published by ``publish``: merged with the
    current version of the index if there is one, and moved in place into
    ``BUILD_DIR``. The steps are recorded into the script; when executing,
    the recorded shell commands of ``publish`` are also run, so the script
    and the run do the same thing.
    """

    def __init__(
        self,
        builder: IndexBuilder,
        mode: ApplyMode,
        config: IndexOpsConfig,
        script: ScriptRecorder,
        paths: BuildPaths,
    ) -> None:
        self._builder = builder
        self._mode = mode
        self._config = config
        self._script = script
        self._paths = paths
        self._claimed = set[str]()
        self._prepared: set[str] = set()

    @property
    def executes(self) -> bool:
        return self._mode.executes

    def has_index(self, name: str) -> bool:
        self._builder.index.load_json()
        return self._builder.index.has_index(name)

    def index_samples(self, name: str) -> set[str]:
        """Samples held by the index ``name``, read from its folder.

        The folder (its ``kmtricks.fof``) is what queries read, so it is the
        truth even when ``index.json`` is behind (a publish interrupted
        between its moves and its registration); ``index.json`` is the
        fallback when the folder is missing.
        """
        fof = os.path.join(self._paths.shard(name), "kmtricks.fof")
        if os.path.isfile(fof):
            with open(fof) as f:
                return {line.split(":", 1)[0].strip() for line in f if line.strip()}
        if self.has_index(name):
            return set(self._builder.index.get_index(name).samples)
        return set()

    def has_folder(self, name: str) -> bool:
        """True if ``BUILD_DIR/<name>`` exists (an index, registered or not)."""
        return os.path.lexists(self._paths.shard(name))

    def register_folder(self, target: str, parts: list[str]) -> None:
        """Register the complete folder ``BUILD_DIR/<target>`` left unregistered.

        A publish interrupted after its moves: nothing is left to build or
        merge, only the runs of ``parts`` (and their chunks) to delete.
        """
        group = self._script.current or target
        self._script.select(ScriptRecorder.merge_group(group))
        self._locked(self._register(target), f"register {target}")
        runs = [self._paths.run(p) for p in parts]
        self._check_and_clean(target, runs, [])
        self._sh(
            "rm -rf " + " ".join(f"{_q(r)}_chunk*" for r in runs),
            f"cleanup {summarize_names(parts)} chunks",
        )
        self._script.select(group)

    def claim(self, name: str) -> bool:
        """Reserve ``name`` for a build in this run. False if already claimed."""
        if name in self._claimed:
            return False
        self._claimed.add(name)
        return True

    def align_with(self, target: str, params: BuildParams) -> BuildParams:
        """Match ``params`` to an already registered ``target``.

        kmindex refuses to merge indexes whose partition count or minimizer
        size differ, so a part joining an existing shard must reuse them.
        """
        if not self.has_index(target):
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
    ) -> dict[str, int]:
        """Build ``i`` as unregistered runs; return their sample count by run name.

        One run named after ``i``, or ``{name}_chunk{n}`` runs when ``params``
        requires chunks.
        """
        assert i.name
        if params.chunk_size is None:
            self._build_run(i.name, fof, i, params)
            return {i.name: fof.get_sample_count()}

        size = params.chunk_size
        items = list(fof.samples.items())
        chunks = [items[n : n + size] for n in range(0, len(items), size)]
        logger.info(
            f"  └── Splitting '{i.name}' into {len(chunks)} chunks of up to "
            f"{size} samples (open-files limit)"
        )
        runs: dict[str, int] = {}
        for n, chunk_items in enumerate(chunks):
            name = f"{i.name}_chunk{n}"
            self._build_run(name, FofManager(samples=dict(chunk_items)), i, params)
            runs[name] = len(chunk_items)
        return runs

    def _build_run(
        self, name: str, fof: FofManager, i: IndexDefinition, params: BuildParams
    ) -> None:
        """Build the kmtricks run ``work/<session>/runs/<name>``.

        A complete run left by an earlier attempt is kept; an incomplete one
        is deleted and rebuilt.
        """
        run_dir = self._paths.run(name)
        if self.executes and os.path.exists(run_dir):
            problems = chunk_problems(run_dir, params.partitions)
            if not problems:
                logger.info(f"  └── Reusing complete run '{name}'")
                return
            logger.info(
                f"  └── Rebuilding incomplete run '{name}': {', '.join(problems)}"
            )
            shutil.rmtree(run_dir)
        if self._mode is ApplyMode.APPLY:
            logger.info(f"  └── Building '{name}'...")

        group = self._script.current or name
        if group not in self._prepared:
            # kmtricks needs the parent of its run directory
            self._script.add(f"mkdir -p {_q(self._paths.runs)}", "prepare")
            self._prepared.add(group)

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
                progress=progress.handler,
                register=False,
            )
            if result and "command" in result:
                self._script.add(result["command"], f"build {name}")

    def publish(
        self,
        i: IndexDefinition,
        target: str,
        runs: dict[str, int],
        params: BuildParams,
        absorbed: list[str] | None = None,
    ) -> None:
        """Publish the runs built for ``target`` as the index ``BUILD_DIR/<target>``.

        ``absorbed`` are other indexes of ``BUILD_DIR`` to merge in, then
        unregister and delete (parts registered by an older kmhelpers).

        Recorded in the merge script of the current group, run after its builds:

        1. check that every run is complete (else stop before touching anything);
        2. a single new run: move it in place and register it;
        3. otherwise merge the runs, plus the current version of ``target`` if
           there is one, in a balanced tree of merges of at most ``k`` inputs
           (``max_inputs``), each in a throwaway registry holding only its
           inputs; then, under the registry lock: unregister ``target``, move
           its current version to ``work/<session>/previous/``, move the result
           in place, register it;
        4. check the published index (before deleting anything);
        5. delete the runs, the merges and the previous version.

        Every step can be run again after an interruption: a merge step whose
        ``done`` marker exists is skipped (all of them once the last one is
        done), and each move is skipped once made. Until the new version is
        registered, ``target`` is either registered with its current folder or
        not registered at all. Moves are renames (``kmhelpers manage move-dir``):
        they fail instead of copying across filesystems.
        """
        paths = self._paths
        partitions = params.partitions
        names = list(runs)
        run_dirs = {name: paths.run(name) for name in names}
        absorbed = absorbed or []
        final_done = self._done(target, target)
        # An interrupted publish may have left target unregistered, or moved away
        existing = (
            self.has_index(target)
            or self.has_folder(target)
            or os.path.exists(final_done)
        )

        group = self._script.current or target
        self._script.select(ScriptRecorder.merge_group(group))

        shard = paths.shard(target)
        single = len(names) == 1 and not existing and not absorbed
        run = run_dirs[names[0]]
        # once merged (or moved in place), the runs may be gone: nothing to check
        published = (
            f"[ ! -e {_q(run)} ] && [ -e {_q(shard)} ]"
            if single
            else f"[ -e {_q(final_done)} ]"
        )

        # 1. every run must be complete before anything is registered
        runs_tsv = self._write_tsv(f"{target}.runs.tsv", run_dirs)
        self._sh(
            f"if {published}; then echo 'runs already used'; else "
            f"{self._check_runs_cmd(runs_tsv, partitions)}; fi",
            f"check {summarize_names(names)}",
        )

        if single:
            # 2. nothing to merge
            self._locked(
                f"{self._move(run, shard)} && {self._register(target)}",
                f"publish {target}",
            )
        else:
            # 3. merge, then swap
            inputs = dict(run_dirs)
            samples = dict(runs)
            if existing:
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                current = backup_name(target, stamp)
                inputs[current] = shard
                samples[current] = len(self.index_samples(target))
            for name in absorbed:
                inputs[name] = paths.shard(name)
                samples[name] = len(self.index_samples(name))
            out = self._merge(i, target, inputs, samples, params)

            previous = paths.previous(target)
            unregister = shlex.join(
                ["kmhelpers", "manage", "-r", paths.registry, "remove"]
                + [a for n in [target] + absorbed for a in ("-n", n)]
                # the entry's folder (or old-layout symlink) is moved below
                + ["-y", "--missing-ok", "--keep-link"]
            )
            swap = [
                unregister,
                # the current version goes aside only while the result waits
                f"{{ [ ! -e {_q(out)} ] || {self._move(shard, previous)}; }}",
                self._move(out, shard),
                self._register(target),
            ]
            self._locked(" && ".join(swap), f"publish {target}")

        self._check_and_clean(target, list(run_dirs.values()), absorbed)
        self._script.select(group)

    def _check_and_clean(
        self, target: str, run_dirs: list[str], absorbed: list[str]
    ) -> None:
        """Check the published ``target``, then delete what built it."""
        paths = self._paths
        # 4. a broken index must not cost its inputs
        self._sh(
            shlex.join(
                ["kmhelpers", "manage", "-r", paths.registry, "check", "-n", target]
            ),
            f"check {target}",
        )

        # 5. runs, merges and the previous version are no longer needed
        cleanup = run_dirs + [paths.shard(n) for n in absorbed] + [paths.merges(target)]
        if not self._config.keep_previous:
            cleanup.append(paths.previous(target))
        self._remove(cleanup, f"cleanup {target}")
        work_dirs = [
            paths.runs,
            os.path.dirname(paths.merges(target)),
            os.path.dirname(paths.previous(target)),
            paths.work,
            os.path.dirname(paths.work),
        ]
        self._sh(
            "rmdir --ignore-fail-on-non-empty "
            + " ".join(_q(d) for d in work_dirs)
            + " 2>/dev/null || true",
            "cleanup work",
        )
        self._builder.index.load_json()

    def _done(self, target: str, step: str) -> str:
        """Marker written once the merge step ``step`` succeeded."""
        return os.path.join(self._paths.merge_step(target, step), "done")

    @staticmethod
    def _move(source: str, destination: str) -> str:
        """Rename, skipped if already made; never a copy."""
        return shlex.join(
            ["kmhelpers", "manage", "move-dir", "--missing-ok", source, destination]
        )

    def _register(self, target: str) -> str:
        return self._kmindex(
            "register",
            "--global-index",
            self._paths.registry,
            "--name",
            target,
            "--index-path",
            self._paths.shard(target),
        )

    def _merge(
        self,
        i: IndexDefinition,
        target: str,
        inputs: dict[str, str],
        samples: dict[str, int],
        params: BuildParams,
    ) -> str:
        """Merge ``inputs`` (name -> index path) into ``target``; return the result path.

        Steps of at most ``k`` inputs, ``k`` set by the resource limits. Each
        step runs in ``merges/<target>/<step>/``: ``registry/`` holds its
        inputs, ``out/`` its result.
        """
        paths = self._paths
        partitions = params.partitions
        threads = merge_threads(params.threads, partitions)
        limits = MergeLimits.resolve(self._config.limits, self._config.safety_margin)
        k, binding = max_inputs(limits, partitions, params.minim_size, threads)
        steps = merge_tree(target, list(inputs), k)
        logger.info(
            f"  └── Merging {len(inputs)} inputs into '{target}': "
            f"{len(steps)} merge(s), at most {k} inputs each ({binding} limit), "
            f"{threads} thread(s)"
        )

        def out_of(name: str) -> str:
            return inputs.get(name) or os.path.join(
                paths.merge_step(target, name), "out"
            )

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

            step_dir = paths.merge_step(target, step.name)
            registry = os.path.join(step_dir, "registry")
            tsv = self._write_tsv(
                f"{step.name}.register.tsv", {n: out_of(n) for n in step.inputs}
            )
            done = self._done(target, step.name)
            run_step = " && ".join(
                [
                    # kmindex creates the registry; it must not exist without index.json
                    f"rm -rf {_q(step_dir)}",
                    f"mkdir -p {_q(step_dir)}",
                    self._kmindex(
                        "register", "--global-index", registry, "--from-file", tsv
                    ),
                    self._kmindex(
                        "merge",
                        "--index",
                        registry,
                        "--new-name",
                        step.name,
                        "--new-path",
                        os.path.join(step_dir, "out"),
                        "--to-merge",
                        ",".join(step.inputs),
                        "--threads",
                        str(threads),
                    ),
                    f"touch {_q(done)}",
                ]
            )
            self._sh(
                f"if [ -e {_q(done)} ] || [ -e {_q(self._done(target, target))} ]; "
                f"then echo 'already merged'; else {run_step}; fi",
                f"merge {summarize_names(step.inputs)} -> {step.name}",
            )
            consumed = [
                paths.merge_step(target, n) for n in step.inputs if n not in inputs
            ]
            self._remove([registry] + consumed, f"cleanup {step.name} registry")
        return out_of(target)

    @staticmethod
    def _kmindex(*args: str) -> str:
        return shlex.join(["kmindex", *args, "--verbose", "info"])

    def _locked(self, cmd: str, label: str) -> None:
        """Run ``cmd`` holding the registry lock: merge jobs may publish at once."""
        self._sh(f"flock {_q(self._paths.lock)} -c {_q(cmd)}", label)

    def _sh(self, cmd: str, label: str) -> None:
        """Record ``cmd`` into the script; when executing, also run it with bash."""
        self._script.add(cmd, label)
        if not self.executes:
            return
        env = dict(os.environ)
        # kmhelpers and kmindex of this installation come first
        env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
        r = subprocess.run(
            ["bash", "-c", f"set -euo pipefail\n{cmd}"],
            cwd=self._paths.build_dir,
            env=env,
            capture_output=True,
            text=True,
        )
        if r.stdout:
            logger.debug(r.stdout.rstrip())
        if r.returncode != 0:
            tail = "\n".join((r.stderr or r.stdout).strip().splitlines()[-20:])
            raise RuntimeError(f"'{label}' failed (exit {r.returncode}):\n{tail}")

    def _write_tsv(self, file_name: str, entries: dict[str, str]) -> str:
        """Write ``name<TAB>path`` lines to the assets folder; return the file path."""
        path = os.path.join(self._paths.assets, file_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.writelines(f"{name}\t{p}\n" for name, p in entries.items())
        return path

    @staticmethod
    def _check_runs_cmd(runs_tsv: str, partitions: int) -> str:
        """Shell loop stopping the script when a kmtricks run is incomplete.

        Same test as ``chunk_problems``: kmtricks writes ``run_infos.txt`` only
        after its last stage; all ``partitions`` matrices must be non-empty and
        of one size.
        """
        return (
            "bad=0; while IFS=$'\\t' read -r name dir; do "
            'n=$(ls "$dir"/matrices/matrix_*.cmbf 2>/dev/null | wc -l); '
            'sizes=$(stat -c %s "$dir"/matrices/matrix_*.cmbf 2>/dev/null | sort -u); '
            'if [ ! -s "$dir/run_infos.txt" ] || [ ! -f "$dir/kmtricks.fof" ] '
            '|| [ ! -f "$dir/options.txt" ] '
            f'|| [ "$n" -ne {partitions} ] || [ "$(echo "$sizes" | wc -l)" -ne 1 ] '
            '|| [ "$sizes" = 0 ]; then '
            'echo "incomplete run: $name ($dir)" >&2; bad=$((bad + 1)); fi; '
            f"done < {_q(runs_tsv)}; "
            'if [ "$bad" -gt 0 ]; then echo "$bad incomplete run(s): not publishing" >&2; '
            "exit 1; fi"
        )

    def _remove(self, paths: list[str], label: str) -> None:
        """Delete ``paths``, and the target of those that are symlinks."""
        if not paths:
            return
        quoted = " ".join(_q(p) for p in paths)
        self._sh(
            # cd -P resolves a symlink portably (no GNU realpath -m)
            f"for d in {quoted}; do "
            'if p=$(cd -P "$d" 2>/dev/null && pwd); then rm -rf "$p"; fi; '
            'rm -rf "$d"; done',
            label,
        )
