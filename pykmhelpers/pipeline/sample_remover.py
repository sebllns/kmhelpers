"""Remove samples from built shards: their columns are dropped from every matrix.

A shard is rewritten in ``BUILD_DIR/work/remove-samples/<shard>/``::

    new/        the shard without the removed samples
    registry/   throwaway registry, to check new/ before it is published
    checked     marker: new/ passed its check
    previous/   the replaced version, during the swap

The swap runs under the registry lock: the shard is unregistered, its folder
moved to ``previous/``, then ``kmindex register --mode move`` moves ``new/`` in
place and registers it. Every move is a rename, so the shard and ``work/`` must
be on one filesystem. An interrupted removal is finished or undone by the
next run (``recover``).
"""

import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from pykmhelpers.core.file_lock import locked
from pykmhelpers.core.index import KmindexRegistry
from pykmhelpers.core.kmindex_layout import get_bytes_per_row, get_header_byte_size
from pykmhelpers.core.kmindex_wrapper import KmindexWrapper
from pykmhelpers.pipeline.index_ops.report import dir_bytes
from pykmhelpers.pipeline.query_check import MIN_GAP, query_check

logger = logging.getLogger(__name__)

WORK_DIR = "remove-samples"
CHECKED = "checked"

_MATRIX = re.compile(r"matrices/matrix_\d+\.cmbf")
_SUM = re.compile(r"matrices/sum_\d+\.vec")
_FPR = re.compile(r"fpr/partition_\d+\.txt")
_FOF = "kmtricks.fof"

# Raw bytes read per chunk; unpacked, a chunk takes 8 times more
_CHUNK_BYTES = 16 << 20


def drop_columns(
    src: str,
    dst: str,
    nb_samples: int,
    bw: int,
    removed: Iterable[int],
    chunk_bytes: int = _CHUNK_BYTES,
) -> None:
    """Write the matrix ``src`` to ``dst`` without the samples at ``removed``.

    A row holds ``bw`` bits per sample, sample ``s`` on bits
    ``[s*bw, (s+1)*bw)``, least significant bit first (kmindex BITCHECK). The
    49-byte header is copied as is: kmindex does not read its sample count.
    """
    header = get_header_byte_size()
    gone = set(removed)
    kept = [s for s in range(nb_samples) if s not in gone]
    old_row = get_bytes_per_row(nb_samples * bw)
    new_row = get_bytes_per_row(len(kept) * bw)
    body = os.path.getsize(src) - header
    if body < 0 or body % old_row:
        raise ValueError(
            f"{src}: {body} bytes after the header is not a whole number of "
            f"{old_row}-byte rows ({nb_samples} samples, bw={bw})"
        )
    rows = body // old_row
    keep_bits = (np.asarray(kept)[:, None] * bw + np.arange(bw)).ravel()
    step = max(1, chunk_bytes // old_row)

    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(fin.read(header))
        for start in range(0, rows, step):
            n = min(step, rows - start)
            block = np.frombuffer(fin.read(n * old_row), dtype=np.uint8)
            bits = np.unpackbits(block.reshape(n, old_row), axis=1, bitorder="little")
            out = np.packbits(bits[:, keep_bits], axis=1, bitorder="little")
            fout.write(out.tobytes())

    size = os.path.getsize(dst)
    if size != header + rows * new_row:
        raise RuntimeError(f"{dst}: {size} bytes written, {header + rows * new_row} expected")


def fof_names(text: str) -> list[str]:
    """Sample names of a kmtricks.fof, in file (column) order."""
    return [n for n in (line.split(":", 1)[0].strip() for line in text.splitlines()) if n]


@dataclass
class ShardRemoval:
    """Samples to remove from one shard, as read before any change."""

    shard: str
    samples: list[str]
    removed: list[str]
    fof: str
    bw: int
    nb_partitions: int

    @property
    def removed_idx(self) -> list[int]:
        gone = set(self.removed)
        return [i for i, s in enumerate(self.samples) if s in gone]


class SampleRemover:
    """Remove samples from the shards of the registry ``registry_path``.

    Args:
        registry_path: The kmindex registry (``BUILD_DIR``).
        threads: Matrices rewritten at once.
        check: Check each new shard (structure and query) before publishing it.
        zvalue: z of the query check.
        min_gap: A new shard whose positive score is not this far above its
            negative score fails its check.
    """

    def __init__(
        self,
        registry_path: str,
        threads: int = 1,
        check: bool = True,
        zvalue: int = 6,
        min_gap: float = MIN_GAP,
        query_count: int = 10,
    ) -> None:
        self._root = os.path.realpath(registry_path)
        self._threads = threads
        self._check = check
        self._zvalue = zvalue
        self._min_gap = min_gap
        self._query_count = query_count
        self._kmindex = KmindexWrapper()

    @property
    def work(self) -> str:
        return os.path.join(self._root, "work", WORK_DIR)

    def work_dir(self, shard: str) -> str:
        return os.path.join(self.work, shard)

    def shard_path(self, shard: str) -> str:
        """Registry entry of ``shard``: its folder, or a link to it."""
        return os.path.join(self._root, shard)

    def _registry(self) -> KmindexRegistry:
        return KmindexRegistry(self._root, auto_create=False)

    def _lock(self) -> locked:
        return locked(os.path.join(self._root, ".registry.lock"))

    # ---
    # PUBLIC METHODS

    def recover(self) -> list[str]:
        """Finish or undo the removals an interruption left; return what was done."""
        if not os.path.isdir(self.work):
            return []
        done = []
        with self._lock():
            for shard in sorted(os.listdir(self.work)):
                done.append(f"{shard}: {self._recover(shard)}")
        self._clean_work()
        return done

    def resolve(
        self, names: Iterable[str], shards: list[str]
    ) -> tuple[list[ShardRemoval], set[str]]:
        """Group ``names`` by the shards of ``shards`` holding them; return the
        removals and the names found in none. A name in several shards is
        removed from each."""
        wanted = set(names)
        registry = self._registry()
        removals = []
        found: set[str] = set()
        for shard in shards:
            with open(os.path.join(self.shard_path(shard), _FOF)) as f:
                text = f.read()
            samples = fof_names(text)
            removed = [s for s in samples if s in wanted]
            if not removed:
                continue
            props = registry.get_index_properties(shard)
            removals.append(
                ShardRemoval(
                    shard=shard,
                    samples=samples,
                    removed=removed,
                    fof=text,
                    bw=max(int(props.get("bw", 1)), 1),
                    nb_partitions=int(props["nb_partitions"]),
                )
            )
            found.update(removed)
        return removals, wanted - found

    def problems(self, r: ShardRemoval) -> list[str]:
        """Why ``r`` cannot be done; empty when it can."""
        real = os.path.realpath(self.shard_path(r.shard))
        issues = []
        if len(r.removed) == len(r.samples):
            issues.append("every sample would be removed: remove the shard instead")
        if os.path.exists(os.path.join(real, "compression.cfg")) or os.path.exists(
            os.path.join(real, "matrices", "blocks0")
        ):
            issues.append("compressed: the uncompressed matrices are needed")
        missing = [
            p
            for p in range(r.nb_partitions)
            if not os.path.isfile(os.path.join(real, "matrices", f"matrix_{p}.cmbf"))
        ]
        if missing:
            issues.append(f"{len(missing)} matrix file(s) missing")
        nb_samples = self._registry().get_index_properties(r.shard)["nb_samples"]
        if nb_samples != len(r.samples):
            issues.append(
                f"index.json holds {nb_samples} samples, its kmtricks.fof {len(r.samples)}"
            )
        if os.stat(real).st_dev != os.stat(self._root).st_dev:
            issues.append(f"{real} and {self._root} are not on the same filesystem: not copying")
        return issues

    def remove(self, r: ShardRemoval) -> tuple[int, int]:
        """Rewrite the shard of ``r`` without its removed samples, check it and
        publish it; return the bytes of its matrices before and after."""
        work = self.work_dir(r.shard)
        new = os.path.join(work, "new")
        previous = os.path.join(work, "previous")
        real = os.path.realpath(self.shard_path(r.shard))
        before = dir_bytes(os.path.join(real, "matrices"))

        os.makedirs(work)
        try:
            logger.info(f"{r.shard}: writing {len(r.samples) - len(r.removed)} samples to {new}")
            self._write_new(r, real, new)
            if self._check:
                self._check_new(r.shard, work, new)
            open(os.path.join(work, CHECKED), "w").close()
        except BaseException:
            # nothing published yet: the shard is untouched
            shutil.rmtree(work, ignore_errors=True)
            self._clean_work()
            raise
        after = dir_bytes(os.path.join(new, "matrices"))

        with self._lock():
            with open(os.path.join(self.shard_path(r.shard), _FOF)) as f:
                changed = f.read() != r.fof
            if not changed:
                self._registry().remove_index(r.shard)
                os.rename(real, previous)
                self._publish(r.shard, new)
        shutil.rmtree(work)
        self._clean_work()
        if changed:
            raise RuntimeError(f"{r.shard} changed during the removal: not published")
        return before, after

    # ---
    # PRIVATE METHODS

    def _publish(self, shard: str, new: str) -> None:
        """Move ``new`` in place as ``shard`` and register it."""
        self._kmindex.register(self._root, name=shard, index_path=new, mode="move")

    def _recover(self, shard: str) -> str:
        work = self.work_dir(shard)
        new = os.path.join(work, "new")
        previous = os.path.join(work, "previous")
        entry = self.shard_path(shard)
        registry = self._registry()
        if os.path.lexists(entry):
            if not registry.has_index(shard):
                # moved in place (or not moved yet) but not registered
                self._kmindex.register(self._root, name=shard, index_path=entry)
                result = "registered its folder"
            else:
                result = "left as registered"
        elif os.path.isfile(os.path.join(work, CHECKED)) and os.path.isdir(new):
            if registry.has_index(shard):
                registry.remove_index(shard)
            self._publish(shard, new)
            result = "new version published"
        elif os.path.isdir(previous):
            os.rename(previous, entry)
            if not registry.has_index(shard):
                self._kmindex.register(self._root, name=shard, index_path=entry)
            result = "previous version restored"
        else:
            raise RuntimeError(
                f"{shard}: interrupted removal with no shard folder and nothing to "
                f"restore, see {work}"
            )
        shutil.rmtree(work)
        return result

    def _write_new(self, r: ShardRemoval, src: str, new: str) -> None:
        """Write ``new``: matrices, fof and fpr rewritten, other files hardlinked."""
        gone = set(r.removed)
        idx = r.removed_idx
        matrices = []
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            out_dir = os.path.normpath(os.path.join(new, rel))
            os.makedirs(out_dir, exist_ok=True)
            for name in [d for d in dirs if os.path.islink(os.path.join(root, d))]:
                dirs.remove(name)
                os.symlink(os.readlink(os.path.join(root, name)), os.path.join(out_dir, name))
            for name in files:
                rel_file = os.path.normpath(os.path.join(rel, name))
                s, d = os.path.join(root, name), os.path.join(out_dir, name)
                if os.path.islink(s):
                    os.symlink(os.readlink(s), d)
                elif rel_file == _FOF:
                    with open(d, "w") as f:
                        f.writelines(
                            line
                            for line in r.fof.splitlines(keepends=True)
                            if line.split(":", 1)[0].strip() not in gone
                        )
                elif _MATRIX.fullmatch(rel_file):
                    matrices.append((s, d))
                elif _SUM.fullmatch(rel_file):
                    # sum index: no longer valid
                    continue
                elif _FPR.fullmatch(rel_file):
                    self._filter_fpr(s, d, len(r.samples), set(idx))
                else:
                    _link(s, d)

        def rewrite(paths: tuple[str, str]) -> None:
            drop_columns(paths[0], paths[1], len(r.samples), r.bw, idx)

        with ThreadPoolExecutor(max_workers=self._threads) as pool:
            list(pool.map(rewrite, matrices))

    @staticmethod
    def _filter_fpr(src: str, dst: str, nb_samples: int, removed: set[int]) -> None:
        # one line per sample, in fof order
        with open(src) as f:
            lines = [line for line in f if line.strip()]
        if len(lines) != nb_samples:
            logger.warning(f"{src}: {len(lines)} lines for {nb_samples} samples, kept as is")
            _link(src, dst)
            return
        with open(dst, "w") as f:
            f.writelines(line for i, line in enumerate(lines) if i not in removed)

    def _check_new(self, shard: str, work: str, new: str) -> None:
        """Check ``new`` (structure and query) in a throwaway registry."""
        path = os.path.join(work, "registry")
        self._kmindex.register(path, name=shard, index_path=new)
        try:
            registry = KmindexRegistry(path, auto_create=False)
            if not registry.get_index(shard).check_structure():
                raise RuntimeError(f"{shard}: the new version has an invalid structure")
            check = query_check(registry, [shard], self._zvalue, self._query_count)[shard]
            logger.info(f"{shard}: query check {check.summary()}")
            if check.broken(self._min_gap):
                raise RuntimeError(
                    f"{shard}: the new version fails its query check "
                    f"(positive {check.mean:.3f}, negative {check.neg_mean:.4f})"
                )
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def _clean_work(self) -> None:
        for d in (self.work, os.path.dirname(self.work)):
            try:
                os.rmdir(d)
            except OSError:
                pass


def _link(src: str, dst: str) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
