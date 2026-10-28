"""Resume an interrupted ``kmtricks pipeline`` run with its individual steps.

``kmtricks pipeline`` refuses an existing run directory, so an interrupted run
used to be deleted and rebuilt. This module reads how far the run got and runs
``superk``, ``count`` and ``merge`` only for the parts left unfinished. Markers
(kmtricks v1.6.0, observed by killing runs at various points):

- repart is done once ``superkmers/`` holds an entry;
- ``superk`` of a sample is done once ``partition_infos/<id>.pinfo`` exists;
- ``count`` of a sample and partition is done once its count file exists and
  ``superkmers/<id>/skp.<p>`` is gone (the pipeline deletes it after counting);
- ``merge`` of a partition is done once ``merge_infos/partition<p>.merge_info``
  exists (written after the matrix).

Unfinished work is redone at the smallest of these grains: a partition of a
sample when its super-k-mers are complete, else the whole sample.
"""

import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from pykmhelpers.core.kmindex_layout import load_options_file

logger = logging.getLogger(__name__)

# Exit status of ``kmhelpers manage resume-run`` when the run must be rebuilt
NOT_RESUMABLE = 3


@dataclass(frozen=True)
class RunSpec:
    """The kmtricks run a build script expects in ``run_dir``."""

    run_dir: Path
    fof: Path
    partitions: int
    kmer_size: int
    minim_size: int
    bloom_size: int
    hard_min: int
    bitw: Optional[int] = None
    compress: bool = False

    @property
    def merge_mode(self) -> str:
        return "hash:bfc:bin" if self.bitw else "hash:bf:bin"

    def count_file(self, sample: str, partition: int) -> Path:
        suffix = ".p4" if self.compress else ""
        return (
            self.run_dir
            / "counts"
            / f"partition_{partition}"
            / f"{sample}.hash{suffix}"
        )

    def skp_file(self, sample: str, partition: int) -> Path:
        return self.run_dir / "superkmers" / sample / f"skp.{partition}"

    def pinfo_file(self, sample: str) -> Path:
        return self.run_dir / "partition_infos" / f"{sample}.pinfo"

    def merge_info_file(self, partition: int) -> Path:
        return self.run_dir / "merge_infos" / f"partition{partition}.merge_info"


@dataclass
class ResumePlan:
    """Work left in a run: samples to rebuild, partitions to count and merge."""

    superk: list[str] = field(default_factory=list)
    count: dict[str, list[int]] = field(default_factory=dict)
    merge: list[int] = field(default_factory=list)

    def summary(self) -> str:
        n_count = sum(len(p) for p in self.count.values())
        return (
            f"superk {len(self.superk)} sample(s), count {n_count} sample partition(s), "
            f"merge {len(self.merge)} partition(s)"
        )


def fof_samples(fof: Path) -> list[str]:
    """Sample IDs of a kmtricks fof, in file order."""
    samples = []
    with open(fof) as f:
        for line in f:
            sample = line.split(":", 1)[0].strip()
            if sample:
                samples.append(sample)
    return samples


def _options_mismatch(spec: RunSpec) -> list[str]:
    """Options the run was started with that differ from ``spec``."""
    options = load_options_file(str(spec.run_dir / "options.txt"))
    expected = {
        "kmer_size": spec.kmer_size,
        "minim_size": spec.minim_size,
        "nb_partitions": spec.partitions,
        "bloom_size": spec.bloom_size,
        "c_ab_min": spec.hard_min,
        "lz4": int(spec.compress),
        "mode": "bfc" if spec.bitw else "bf",
        "count_format": "hash",
    }
    if spec.bitw:
        expected["bwidth"] = spec.bitw
    return [
        f"{key}={options.get(key)!r} (expected {value!r})"
        for key, value in expected.items()
        if options.get(key) != value
    ]


def plan_resume(spec: RunSpec) -> tuple[Optional[ResumePlan], str]:
    """Work left to finish the run in ``spec.run_dir``.

    Returns ``(None, reason)`` when the run cannot be resumed and must be
    rebuilt: no repart yet, another sample list, or other options.
    Time and memory: O(samples x partitions) ``stat`` calls.
    """
    run = spec.run_dir
    if not (run / "options.txt").is_file() or not (run / "kmtricks.fof").is_file():
        return None, "no options.txt or kmtricks.fof"
    if (run / "kmtricks.fof").read_bytes() != spec.fof.read_bytes():
        return None, "other sample list"
    mismatch = _options_mismatch(spec)
    if mismatch:
        return None, "other options: " + ", ".join(mismatch)
    superkmers = run / "superkmers"
    if not superkmers.is_dir() or not any(superkmers.iterdir()):
        return None, "repart not done"

    plan = ResumePlan()
    plan.merge = [
        p for p in range(spec.partitions) if not spec.merge_info_file(p).is_file()
    ]
    for sample in fof_samples(spec.fof):
        if not spec.pinfo_file(sample).is_file():
            plan.superk.append(sample)
            continue
        todo = []
        for p in plan.merge:
            has_count = spec.count_file(sample, p).is_file()
            has_skp = spec.skp_file(sample, p).is_file()
            if has_skp:
                todo.append(p)  # not counted, or count possibly cut short
            elif not has_count:
                break  # nothing to count from: rebuild the sample
        else:
            if todo:
                plan.count[sample] = todo
            continue
        plan.superk.append(sample)
    for sample in plan.superk:
        plan.count[sample] = list(plan.merge)
    return plan, ""


Runner = Callable[[list[str]], None]


def _run(cmd: list[str]) -> None:
    logger.info(" ".join(cmd))
    subprocess.run(cmd, check=True)


class RunResumer:
    """Runs the steps of a ``ResumePlan`` with the kmtricks binary ``kmtricks``.

    Samples run ``jobs`` at a time with ``threads // jobs`` threads each, then
    partitions are merged one after the other with ``threads`` threads.
    """

    def __init__(
        self,
        spec: RunSpec,
        threads: int,
        jobs: int = 1,
        kmtricks: str = "kmtricks",
        runner: Runner = _run,
    ) -> None:
        self.spec = spec
        self.threads = max(1, threads)
        self.jobs = max(1, min(jobs, self.threads))
        self.kmtricks = kmtricks
        self._run = runner

    def _common(self, threads: int) -> list[str]:
        args = ["--run-dir", str(self.spec.run_dir), "-t", str(threads)]
        return args + (["--cpr"] if self.spec.compress else [])

    def _sample(self, sample: str, partitions: list[int], superk: bool) -> None:
        spec = self.spec
        threads = max(1, self.threads // self.jobs)
        if superk:
            shutil.rmtree(spec.run_dir / "superkmers" / sample, ignore_errors=True)
            spec.pinfo_file(sample).unlink(missing_ok=True)
            self._run([self.kmtricks, "superk", "--id", sample] + self._common(threads))
        for p in partitions:
            spec.count_file(sample, p).unlink(missing_ok=True)
            self._run(
                [
                    self.kmtricks,
                    "count",
                    "--id",
                    sample,
                    "--partition-id",
                    str(p),
                    "--mode",
                    "hash",
                    "--hard-min",
                    str(spec.hard_min),
                ]
                + self._common(threads)
            )
            # as the pipeline does; also marks this count as complete
            spec.skp_file(sample, p).unlink(missing_ok=True)

    def _merge(self, partition: int, samples: list[str]) -> None:
        spec = self.spec
        missing = [s for s in samples if not spec.count_file(s, partition).is_file()]
        if missing:
            raise RuntimeError(
                f"partition {partition}: {len(missing)} sample(s) without counts, "
                f"e.g. {missing[0]}"
            )
        spec.merge_info_file(partition).unlink(missing_ok=True)
        (spec.run_dir / "matrices" / f"matrix_{partition}.cmbf").unlink(missing_ok=True)
        self._run(
            [
                self.kmtricks,
                "merge",
                "--partition-id",
                str(partition),
                "--mode",
                spec.merge_mode,
            ]
            + self._common(self.threads)
        )
        # as the pipeline does once a partition is merged
        for s in samples:
            spec.count_file(s, partition).unlink(missing_ok=True)

    def resume(self, plan: ResumePlan) -> None:
        superk = set(plan.superk)
        pool = ThreadPoolExecutor(max_workers=self.jobs)
        futures = [
            pool.submit(self._sample, s, parts, s in superk)
            for s, parts in plan.count.items()
        ]
        try:
            for f in as_completed(futures):
                f.result()
        finally:
            # on a failure, start no other sample
            pool.shutdown(cancel_futures=True)
        samples = fof_samples(self.spec.fof)
        for p in plan.merge:
            self._merge(p, samples)
