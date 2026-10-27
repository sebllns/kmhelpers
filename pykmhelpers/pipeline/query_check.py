"""Query check of registered shards.

Takes a few random (k+z)-mers from the first sample of each shard, queries them
all at once against the registry and reports the score of that sample on its
own records. The score is only reported: a broken shard shows a low score, a
failing kmindex query raises.
"""

import os
import random
import re
import tempfile
from dataclasses import dataclass
from typing import Optional

from pykmhelpers.core.index import IndexCompressionState, KmindexRegistry
from pykmhelpers.core.utils import open_decompressed
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.query import KmindexQuery

# Sequence read from a sample before picking windows, keeps large samples cheap
SCAN_BASES = 1_000_000
_NON_ACGT = re.compile("[^ACGT]+")
_SEP = "__"


@dataclass
class ShardQueryCheck:
    """Score of a shard's first sample on its own records, or why it was skipped."""

    sample: str = ""
    scores: Optional[list[float]] = None
    skipped: str = ""

    @property
    def perfect(self) -> int:
        return sum(s >= 1.0 - 1e-9 for s in self.scores or [])

    def summary(self) -> str:
        if self.skipped:
            return f"skipped ({self.skipped})"
        scores = self.scores or []
        if not scores:
            return f"{self.sample}: no score"
        return (
            f"{self.sample} mean {sum(scores) / len(scores):.3f}, min {min(scores):.3f}, "
            f"{self.perfect}/{len(scores)} perfect"
        )


def first_sample_file(fof_path: str) -> tuple[str, str]:
    """Return the first sample of a kmtricks.fof and its first file."""
    with open(fof_path) as f:
        for line in f:
            parsed = FofManager.parse_fof_line(line)
            if parsed:
                name, paths = parsed
                # "a.fa ; b.fa ! 2": first file, without the per-sample abundance
                path = FofManager().split_path(paths.split("!", 1)[0])[0].strip()
                return name, path
    raise ValueError(f"no sample in {fof_path}")


def _records(path: str):
    """Yield the sequences of a FASTA or FASTQ file (any supported compression)."""
    with open_decompressed(path) as f:
        seq: list[str] = []
        fastq = None
        lines = (raw.decode("ascii", "replace").rstrip("\r\n") for raw in f)
        for line in lines:
            if fastq is None and line:
                fastq = line.startswith("@")
            if fastq:
                if line.startswith("@"):
                    yield next(lines, "")
                    next(lines, None)  # +
                    next(lines, None)  # qualities
            elif line.startswith(">"):
                if seq:
                    yield "".join(seq)
                seq = []
            else:
                seq.append(line)
        if seq:
            yield "".join(seq)


def random_windows(
    path: str, length: int, count: int, rng: random.Random, scan: int = SCAN_BASES
) -> list[str]:
    """Pick ``count`` random ACGT windows of ``length`` bases from the start of a sample.

    Fewer are returned when the first ``scan`` bases do not hold enough.
    """
    # ACGT runs long enough for a window, a run of n bases holds n - length + 1
    runs: list[str] = []
    scanned = 0
    for seq in _records(path):
        runs.extend(r for r in _NON_ACGT.split(seq.upper()) if len(r) >= length)
        scanned += len(seq)
        if scanned >= scan:
            break
    total = sum(len(r) - length + 1 for r in runs)
    windows = []
    for offset in sorted(rng.sample(range(total), min(count, total))):
        for r in runs:
            n = len(r) - length + 1
            if offset < n:
                windows.append(r[offset : offset + length])
                break
            offset -= n
    return windows


def query_check(
    registry: KmindexRegistry,
    names: list[str],
    z: int,
    count: int = 10,
    rng: Optional[random.Random] = None,
) -> dict[str, ShardQueryCheck]:
    """Query ``count`` random (k+z)-mers of each shard's first sample against the registry.

    Raises when kmindex fails; a shard without a usable sample file is skipped.
    """
    rng = rng or random.Random()
    checks: dict[str, ShardQueryCheck] = {}
    windows: dict[str, list[str]] = {}
    for name in names:
        index = registry.get_index(name)
        try:
            sample, path = first_sample_file(index.fof_path)
            if not os.path.isfile(path):
                raise ValueError(f"sample file not found: {path}")
            picked = random_windows(path, index.kmer_size + z, count, rng)
            if not picked:
                raise ValueError(f"no {index.kmer_size + z}-mer in {path}")
        except Exception as e:
            checks[name] = ShardQueryCheck(skipped=str(e) or type(e).__name__)
            continue
        checks[name] = ShardQueryCheck(sample=sample)
        windows[name] = picked

    # query2 for compressed shards, so one query per kind
    groups: dict[bool, list[str]] = {}
    for name in windows:
        compressed = (
            registry.get_index(name).compress_state == IndexCompressionState.COMPRESSED
        )
        groups.setdefault(compressed, []).append(name)

    for compressed, group in groups.items():
        with tempfile.TemporaryDirectory(prefix="kmhelpers_check_") as tmp:
            fasta = os.path.join(tmp, "check.fa")
            with open(fasta, "w") as f:
                for name in group:
                    for i, w in enumerate(windows[name]):
                        f.write(f">{name}{_SEP}{i}\n{w}\n")
            results = KmindexQuery(path=fasta).execute(
                registry_path=registry.root_path,
                output_dir=os.path.join(tmp, "out"),
                index_ids=group,
                z=z,
                threshold=0.0,
                is_compressed=compressed,
            )
            if not results:
                raise RuntimeError("kmindex query wrote no result")
            items: dict = {}
            for r in results:
                for index, queries in r.items.items():
                    items.setdefault(index, {}).update(queries)
            for name in group:
                check = checks[name]
                queries = items.get(name, {})
                check.scores = [
                    queries.get(f"{name}{_SEP}{i}", {}).get(check.sample, 0.0)
                    for i in range(len(windows[name]))
                ]
    return checks
