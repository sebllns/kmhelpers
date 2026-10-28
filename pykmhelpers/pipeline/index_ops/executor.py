import datetime
import glob
import json
import logging
import os
import shlex
from dataclasses import replace
from typing import Optional

from pykmhelpers.core.byte import ByteCounter, SizeFormat
from pykmhelpers.core.kmindex_layout import load_options_file
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
from pykmhelpers.pipeline.index_ops.script import ScriptRecorder
from pykmhelpers.pipeline.index_ops.sizing import BuildParams
from pykmhelpers.pipeline.index_ops.types import IndexOpsConfig

logger = logging.getLogger(__name__)


def _size(n_bytes: float) -> str:
    return str(ByteCounter.auto(int(n_bytes), SizeFormat.BYTE))


def _q(path: str) -> str:
    return shlex.quote(path)


def _fof_names(path: str) -> str:
    """Shell command printing the sorted sample names of the fof ``path``."""
    return f"awk -F: '{{gsub(/[ \\t]/, \"\", $1); if ($1 != \"\") print $1}}' {_q(path)} | sort"


def _run_complete_cmd(run_dir: str, partitions: int) -> str:
    """Shell test, true when the kmtricks run ``run_dir`` is complete.

    Same test as ``chunk_problems``: kmtricks writes ``run_infos.txt`` only
    after its last stage; all ``partitions`` matrices must be non-empty and
    of one size. Run in a subshell, so a failing command is only a false test.
    """
    d = _q(run_dir)
    return (
        f"( n=$(ls {d}/matrices/matrix_*.cmbf 2>/dev/null | wc -l); "
        f"sizes=$(stat -c %s {d}/matrices/matrix_*.cmbf 2>/dev/null | sort -u); "
        f"[ -s {d}/run_infos.txt ] && [ -f {d}/kmtricks.fof ] && [ -f {d}/options.txt ] "
        f'&& [ "$n" -eq {partitions} ] && [ "$(echo "$sizes" | wc -l)" -eq 1 ] '
        '&& [ -n "$sizes" ] && [ "$sizes" != 0 ] )'
    )


def validate_definition(i: IndexDefinition) -> None:
    if not i.name:
        raise ValueError("IndexDefinition is missing required 'name' field")
    if not i.bf_size > 0:
        raise ValueError(
            f"IndexDefinition {i.name} is missing required 'bf_size' field"
        )


class IndexExecutor:
    """Plans kmtricks runs and their publication as indexes of one registry.

    Every index is built as unregistered kmtricks runs in ``work/<session>/``
    (one, or several chunks), then published by ``publish``: merged with the
    current version of the index if there is one, and moved in place into
    ``BUILD_DIR``. Nothing is run here: every step is recorded into the
    scripts of the task (``set_task``), which ``apply`` runs. Each script can
    be run again after an interruption.
    """

    def __init__(
        self,
        builder: IndexBuilder,
        config: IndexOpsConfig,
        script: ScriptRecorder,
        paths: BuildPaths,
    ) -> None:
        self._builder = builder
        self._config = config
        self._script = script
        self._paths = paths
        self._claimed = set[str]()
        self._task_dir: str | None = None
        self._target: str | None = None
        # Every run name planned
        self.run_names: list[str] = []
        # For the report and the plan: each run planned, each target published
        self.run_details: dict[str, dict] = {}
        self.publish_details: dict[str, dict] = {}

    def set_task(self, task_dir: str, target: str) -> None:
        """Record the next runs and publish step into ``assets/<session>/<task_dir>/``,
        for the index ``target``."""
        self._task_dir = task_dir
        self._target = target

    @property
    def task_dir(self) -> str:
        if self._task_dir is None:
            raise RuntimeError("No task selected")
        return self._task_dir

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
        self._script.select(ScriptRecorder.publish_group(self.task_dir))
        self.publish_details[target] = {"publish": {"mode": "register"}}
        self._locked(self._register(target), f"register {target}")
        runs = [self._paths.run(p) for p in parts]
        self._check_and_clean(target, runs)
        self._sh(
            "rm -rf " + " ".join(f"{_q(r)}_chunk*" for r in runs),
            f"cleanup {summarize_names(parts)} chunks",
        )

    def claim(self, name: str) -> bool:
        """Reserve ``name`` for a build in this run. False if already claimed."""
        if name in self._claimed:
            return False
        self._claimed.add(name)
        return True

    def align_with(
        self, target: str, params: BuildParams, part: Optional[str] = None
    ) -> BuildParams:
        """Match ``params`` to an already registered ``target``, else to a run
        of ``part`` already started in this session.

        kmindex refuses to merge indexes whose partition count or minimizer
        size differ, so a part joining an existing shard must reuse them, and
        the runs of one part (plan then apply, a resumed build) must agree.
        """
        if not self.has_index(target):
            started = self._run_partitions(part) if part else None
            if started and started != params.partitions:
                logger.warning(
                    f"Runs of '{part}' are already built with {started} partitions, "
                    f"not {params.partitions}: building with {started}"
                )
                return replace(params, partitions=started, partitions_source="run")
            return params

        registered = self._builder.index.get_index(target)
        aligned = params
        if registered.nb_partitions and registered.nb_partitions != params.partitions:
            logger.warning(
                f"'{target}' is built with {registered.nb_partitions} partitions, "
                f"not {params.partitions}: building with {registered.nb_partitions} "
                f"(a merge needs the same count)"
            )
            aligned = replace(
                aligned,
                partitions=registered.nb_partitions,
                partitions_source="registered",
            )
        if registered.minim_size and registered.minim_size != params.minim_size:
            logger.warning(
                f"'{target}' is registered with minimizer size "
                f"{registered.minim_size}, not {params.minim_size}: building with "
                f"the registered size"
            )
            aligned = replace(aligned, minim_size=registered.minim_size)
        return aligned

    def _run_partitions(self, part: str) -> Optional[int]:
        """Partition count of a run of ``part`` (or of one of its chunks)
        already in ``work/<session>/runs/``, None if there is none."""
        run = self._paths.run(part)
        for run_dir in [run] + sorted(glob.glob(f"{glob.escape(run)}_chunk*")):
            options = os.path.join(run_dir, "options.txt")
            if os.path.isfile(options):
                count = load_options_file(options).get("nb_partitions")
                if count:
                    return int(count)
        return None

    def build(
        self, i: IndexDefinition, fof: FofManager, params: BuildParams
    ) -> dict[str, int]:
        """Plan ``i`` as unregistered runs; return their sample count by run name.

        One run named after ``i``, or ``{name}_chunk{n}`` runs when ``params``
        requires chunks.
        """
        assert i.name
        if params.chunk_size is None:
            planned = {i.name: fof}
        else:
            size = params.chunk_size
            items = list(fof.samples.items())
            chunks = [items[n : n + size] for n in range(0, len(items), size)]
            logger.info(
                f"  └── Splitting '{i.name}' into {len(chunks)} chunks of up to "
                f"{size} samples"
            )
            planned = {
                f"{i.name}_chunk{n}": FofManager(samples=dict(chunk_items))
                for n, chunk_items in enumerate(chunks)
            }
        self.run_names.extend(planned)

        runs: dict[str, int] = {}
        for name, run_fof in planned.items():
            self._build_run(name, run_fof, i, params)
            runs[name] = run_fof.get_sample_count()
        return runs

    def _build_run(
        self, name: str, fof: FofManager, i: IndexDefinition, params: BuildParams
    ) -> None:
        """Record the script building the kmtricks run ``work/<session>/runs/<name>``.

        The script is ``<task dir>/<name>.sh``, its sample list
        ``<task dir>/<name>.fof``. It does nothing when the samples are
        already published in the target, keeps a complete run left by an
        earlier attempt, and deletes and rebuilds an incomplete one.
        """
        run_dir = self._paths.run(name)
        fof_path = os.path.join(self._paths.task(self.task_dir), f"{name}.fof")
        self.run_details[name] = {"samples": fof.get_sample_count(), "action": "planned"}

        self._script.select(f"{self.task_dir}/{name}")
        target_fof = os.path.join(self._paths.shard(self._target or name), "kmtricks.fof")
        self._script.add(
            f"if [ -f {_q(target_fof)} ] && [ -z \"$(comm -23 "
            f"<({_fof_names(fof_path)}) <({_fof_names(target_fof)}))\" ]; then "
            "echo 'samples already published: skip'; exit 0; fi",
            f"check {name}",
        )
        self._script.add(
            f"if {_run_complete_cmd(run_dir, params.partitions)}; then "
            "echo 'complete run: skip'; exit 0; fi",
            f"reuse {name}",
        )
        # kmtricks needs the parent of its run directory, not the run itself
        self._script.add(
            f"rm -rf {_q(run_dir)} && mkdir -p {_q(self._paths.runs)}", "prepare"
        )

        result = self._builder.create_subindex(
            name=name,
            samples=fof,
            abundance_min=i.abundance_min,
            bitw=i.bitw or None,
            bloom_size=i.bf_size,
            n_partitions=params.partitions,
            n_threads=params.threads,
            auto_check=True,
            compress_intermediate=not self._config.kmindex_skip_compression,
            minim_size=params.minim_size,
            dry_run=True,
            kmer_size=i.kmer_size,
            register=False,
            fof_path=fof_path,
        )
        if result and "command" in result:
            self._script.add(result["command"], f"build {name}")

    def publish(
        self,
        i: IndexDefinition,
        target: str,
        runs: dict[str, int],
        params: BuildParams,
    ) -> None:
        """Publish the runs built for ``target`` as the index ``BUILD_DIR/<target>``.

        Recorded in the publish script of the task, run after its builds:

        1. check that every run is complete (else stop before touching anything);
        2. a single new run: check it (structure and query, in a throwaway
           registry), then move it in place and register it;
        3. otherwise merge the runs, plus the current version of ``target`` if
           there is one, in a balanced tree of merges of at most ``k`` inputs
           (``max_inputs``), each in a throwaway registry holding only its
           inputs; check the result as in 2; then, under the registry lock:
           unregister ``target``, move its current version to
           ``work/<session>/previous/``, move the result in place, register it;
        4. check the published index again (before deleting anything);
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
        final_done = self._done(target, target)
        # An interrupted publish may have left target unregistered, or moved away
        existing = (
            self.has_index(target)
            or self.has_folder(target)
            or os.path.exists(final_done)
        )

        self._script.select(ScriptRecorder.publish_group(self.task_dir))

        shard = paths.shard(target)
        single = len(names) == 1 and not existing
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

        details: dict = {"mode": "move" if single else "merge"}
        if existing:
            details["updates"] = target
        self.publish_details[target] = {"publish": details}

        if single:
            # 2. nothing to merge
            self._precheck(target, run)
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
            out = self._merge(i, target, inputs, samples, params, details)
            self._precheck(target, out)

            previous = paths.previous(target)
            # the entry's folder is moved below
            unregister = shlex.join(
                ["kmhelpers", "-Y", "manage", "-r", paths.registry, "remove"]
                + ["--shard", target, "--missing-ok"]
            )
            swap = [
                unregister,
                # the current version goes aside only while the result waits
                f"{{ [ ! -e {_q(out)} ] || {self._move(shard, previous)}; }}",
                self._move(out, shard),
                self._register(target),
            ]
            self._locked(" && ".join(swap), f"publish {target}")

        self._check_and_clean(target, list(run_dirs.values()))

    def _precheck(self, target: str, folder: str) -> None:
        """Check ``folder`` (structure and query) before it is published as
        ``target``, in a throwaway registry holding only it: a broken index
        never reaches the registry. Skipped once ``folder`` is moved in place."""
        paths = self._paths
        registry = os.path.join(paths.merges(target), "precheck")
        published = f"[ ! -e {_q(folder)} ] && [ -e {_q(paths.shard(target))} ]"
        check = " && ".join(
            [
                # kmindex creates the registry; it must not exist without index.json
                f"rm -rf {_q(registry)}",
                f"mkdir -p {_q(paths.merges(target))}",
                self._kmindex(
                    "register", "--global-index", registry,
                    "--name", target, "--index-path", folder,
                ),
                shlex.join(
                    ["kmhelpers", "manage", "-r", registry, "check", "--shard", target]
                ),
            ]
        )
        self._sh(
            f"if {published}; then echo 'already published'; else {check}; fi",
            f"precheck {target}",
        )

    def _check_and_clean(self, target: str, run_dirs: list[str]) -> None:
        """Check the published ``target``, then delete what built it."""
        paths = self._paths
        # 4. a broken index must not cost its inputs
        self._sh(
            shlex.join(
                [
                    "kmhelpers",
                    "manage",
                    "-r",
                    paths.registry,
                    "check",
                    "--shard",
                    target,
                ]
            ),
            f"check {target}",
        )

        # 5. runs, merges and the previous version are no longer needed
        cleanup = run_dirs + [paths.merges(target)]
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
        details: Optional[dict] = None,
    ) -> str:
        """Merge ``inputs`` (name -> index path) into ``target``; return the result path.

        Steps of at most ``k`` inputs, ``k`` set by the resource limits. Each
        step runs in ``merges/<target>/<step>/``: ``registry/`` holds its
        inputs, ``out/`` its result. The steps are added to ``details``.
        """
        paths = self._paths
        partitions = params.partitions
        # a publish job may have other resources than the build jobs (--cluster)
        publish_limits = self._config.publish_limits or self._config.limits
        merge_cpus = json.loads(publish_limits or "{}").get("threads")
        threads = merge_threads(min(params.threads, merge_cpus or params.threads), partitions)
        limits = MergeLimits.resolve(publish_limits, self._config.safety_margin)
        k, binding = max_inputs(limits, partitions, params.minim_size, threads)
        steps = merge_tree(target, list(inputs), k)
        step_details: list[dict] = []
        if details is not None:
            details.update({"threads": threads, "max_inputs": k, "bound_by": binding})
            details["steps"] = step_details
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
                bw=max(i.bitw, 1),
            )
            note = (
                ", more than the RAM limit: relies on page-cache reclaim"
                if fp["mapped"] > limits.ram
                else ""
            )
            step_details.append(
                {
                    "name": step.name,
                    "level": step.level,
                    "inputs": list(step.inputs),
                    "est_anon": _size(fp["anon"]),
                    "est_mapped": _size(fp["mapped"]),
                }
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
        """Run ``cmd`` holding the registry lock: publish jobs may run at once."""
        self._sh(f"flock {_q(self._paths.lock)} -c {_q(cmd)}", label)

    def _sh(self, cmd: str, label: str) -> None:
        """Record ``cmd`` into the selected script."""
        self._script.add(cmd, label)

    def _write_tsv(self, file_name: str, entries: dict[str, str]) -> str:
        """Write ``name<TAB>path`` lines to ``<task dir>/publish/``; return the file path."""
        path = os.path.join(self._paths.task(self.task_dir), "publish", file_name)
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
        """Delete ``paths``."""
        if paths:
            self._sh("rm -rf " + " ".join(_q(p) for p in paths), label)
