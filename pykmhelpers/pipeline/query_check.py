"""Query check of registered shards.

Takes a few random (k+z)-mers from the first sample of each shard and a few
random DNA sequences (negatives), queries them all at once against the registry,
and reports the score of that sample on its own records (positive) and the mean
score of every sample on the negatives (empirical FP rate). A shard whose
positive score is not clearly above its negative score is broken; a failing
kmindex query raises.

When the build recorded the FP rate of the samples (``stats.yaml``, see
``index_ops.stats``), the expected FP rate of a query is reported next to the
empirical one: with findere, a position is a hit when its z+1 k-mers all are.
"""

import os
import random
import re
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from pykmhelpers.core.index import IndexCompressionState, KmindexRegistry
from pykmhelpers.core.utils import open_decompressed
from pykmhelpers.pipeline.fof import FofManager
from pykmhelpers.pipeline.index_ops.stats import load_shard_fpr
from pykmhelpers.pipeline.query import KmindexQuery

# Sequence read from a sample before picking windows, keeps large samples cheap
SCAN_BASES = 1_000_000
# Random DNA queried against every shard: about 10,000 tests per sample
NEG_COUNT = 10
NEG_LENGTH = 1000
# Minimum positive score minus negative score of a sound shard
MIN_GAP = 0.5
_NON_ACGT = re.compile("[^ACGT]+")
_SEP = "__"
# Shard names never start with a dot (check_index_name): no clash with a shard
_NEG = ".neg"


@dataclass
class ShardQueryCheck:
    """Scores of a shard on its first sample and on random DNA, or why it was skipped."""

    sample: str = ""
    scores: Optional[list[float]] = None
    skipped: str = ""
    # sample -> mean score on the negatives
    neg_scores: dict[str, float] = field(default_factory=dict)
    # expected FP rate of a query, from the recorded FP rates of the samples
    expected: Optional[float] = None

    @property
    def perfect(self) -> int:
        return sum(s >= 1.0 - 1e-9 for s in self.scores or [])

    @property
    def mean(self) -> Optional[float]:
        return sum(self.scores) / len(self.scores) if self.scores else None

    @property
    def neg_mean(self) -> Optional[float]:
        if not self.neg_scores:
            return None
        return sum(self.neg_scores.values()) / len(self.neg_scores)

    @property
    def neg_max(self) -> tuple[str, float]:
        worst = max(self.neg_scores, key=lambda n: self.neg_scores[n])
        return worst, self.neg_scores[worst]

    @property
    def gap(self) -> Optional[float]:
        if self.mean is None or self.neg_mean is None:
            return None
        return self.mean - self.neg_mean

    def broken(self, min_gap: float = MIN_GAP) -> bool:
        """The positive score is not clearly above the negative one."""
        return self.gap is not None and self.gap < min_gap

    def suspect(self) -> bool:
        """The empirical FP rate is far above the expected one."""
        if self.expected is None or self.neg_mean is None:
            return False
        return self.neg_mean > max(10 * self.expected, 0.001)

    def summary(self) -> str:
        if self.skipped:
            return f"skipped ({self.skipped})"
        scores = self.scores or []
        if not scores:
            return f"{self.sample}: no score"
        text = (
            f"{self.sample} mean {sum(scores) / len(scores):.3f}, min {min(scores):.3f}, "
            f"{self.perfect}/{len(scores)} perfect"
        )
        if self.neg_scores:
            worst, value = self.neg_max
            text += f"; negatives mean {self.neg_mean:.4f}, max {value:.4f} ({worst})"
            if self.expected is not None:
                text += f", expected {self.expected:.4f}"
        return text


def random_dna(length: int, count: int, rng: random.Random) -> list[str]:
    """``count`` random ACGT sequences of ``length`` bases."""
    return ["".join(rng.choices("ACGT", k=length)) for _ in range(count)]


def expected_fpr(fpr: dict[str, float], z: int) -> Optional[float]:
    """Mean over the samples of the FP rate of a (k+z)-mer: its z+1 k-mers all hit."""
    if not fpr:
        return None
    return sum(v ** (z + 1) for v in fpr.values()) / len(fpr)


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
    neg_count: int = NEG_COUNT,
    neg_length: int = NEG_LENGTH,
) -> dict[str, ShardQueryCheck]:
    """Query ``count`` random (k+z)-mers of each shard's first sample, and
    ``neg_count`` random DNA sequences of ``neg_length`` bases, against the registry.

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
        checks[name] = ShardQueryCheck(
            sample=sample,
            expected=expected_fpr(load_shard_fpr(registry.root_path, name), z),
        )
        windows[name] = picked
    negatives = random_dna(neg_length, neg_count, rng)

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
                for i, seq in enumerate(negatives):
                    f.write(f">{_NEG}{_SEP}{i}\n{seq}\n")
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
                check.neg_scores = negative_scores(
                    queries, registry.get_index(name).samples, len(negatives)
                )
    return checks


def negative_scores(queries: dict, samples: list[str], count: int) -> dict[str, float]:
    """Mean score of each sample over the ``count`` negatives (0 when not reported)."""
    hits = [queries.get(f"{_NEG}{_SEP}{i}", {}) for i in range(count)]
    if not count:
        return {}
    return {s: sum(h.get(s, 0.0) for h in hits) / count for s in samples}
