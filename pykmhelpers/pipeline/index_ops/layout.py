import logging
import os
from typing import Optional

import yaml

from pykmhelpers.core.file_lock import locked, replace_atomically
from pykmhelpers.pipeline.composer import LAYOUT_FILE, layout_lock
from pykmhelpers.pipeline.index_ops.sources import session_dir_of

logger = logging.getLogger(__name__)


class LayoutStore:
    """Read access to the layout of the index being built.

    The layout is written by ``compose``: plan never modifies it. It holds the
    minimizer size, the span base, the partition count of each span when the
    design fixes it (``-P``), the shard capacity of each span and, once a
    shard is published, the partition count it is built with (written by
    ``apply``, see ``record_shard_partitions``).

    Without a layout file (an index definition passed directly), every getter
    returns ``None``.
    """

    def __init__(self, path: Optional[str]) -> None:
        self._path = path
        self._data: dict = {}
        if path and os.path.isfile(path):
            with open(path) as f:
                loaded = yaml.safe_load(f) or {}
            if loaded.get("type") == "layout":
                self._data = loaded
            else:
                logger.warning(f"Not a layout file, ignored: {path}")

    @classmethod
    def next_to(cls, input_file: str) -> "LayoutStore":
        """Layout of the index of ``COMPOSE_DIR/NAME/SESSION/index.yaml`` (or of a
        shard file of the session): ``COMPOSE_DIR/NAME/layout.yaml``."""
        index_dir = os.path.dirname(session_dir_of(input_file))
        return cls(os.path.join(index_dir, LAYOUT_FILE))

    @property
    def path(self) -> Optional[str]:
        """The layout file, when there is one."""
        return self._path if self._path and os.path.isfile(self._path) else None

    @property
    def exists(self) -> bool:
        return bool(self._data)

    def minim_size(self) -> Optional[int]:
        return self._get(self._payload(), "minim_size")

    def base(self) -> Optional[float]:
        """Base of the spans: span s holds samples of base**s to base**(s+1) k-mers."""
        value = (self._payload() or {}).get("base")
        return float(value) if value else None

    def partition_count(self, span: int) -> Optional[int]:
        return self._get(self._span(span), "partition_count")

    def shard_partition_count(self, shard: str) -> Optional[int]:
        """Partition count shard ``shard`` is published with, None before."""
        return self._get(self._shard(shard), "partition_count")

    def sample_budget(self, span: int) -> Optional[int]:
        """Samples the partition count should be sized for.

        The shard capacity when sharding is on, else what the span holds.
        """
        return self._get(self._span(span), "max_samples") or self._get(
            self._span(span), "total_samples"
        )

    # ---

    def _payload(self) -> Optional[dict]:
        return self._data.get("data") if self._data else None

    def _span(self, span: int) -> Optional[dict]:
        payload = self._payload()
        entry = (payload or {}).get("map", {}).get(span)
        # A span mapped to a plain name predates these fields
        return entry if isinstance(entry, dict) else None

    def _shard(self, shard: str) -> Optional[dict]:
        return _find_shard((self._payload() or {}).get("map") or {}, shard)

    @staticmethod
    def _get(entry: Optional[dict], key: str) -> Optional[int]:
        value = (entry or {}).get(key)
        return int(value) if value else None


def _find_shard(span_map: dict, shard: str) -> Optional[dict]:
    """Entry of ``shard`` in the shards of a layout map, None if not listed."""
    for entry in span_map.values():
        if not isinstance(entry, dict):
            continue
        for sh in entry.get("shards") or []:
            if isinstance(sh, dict) and sh.get("name") == shard:
                return sh
    return None


def record_shard_partitions(path: str, shard: str, count: int) -> bool:
    """Record in the layout ``path`` the partition count ``shard`` is published
    with; True when the layout was written.

    Only a missing count is filled: a recorded count is never changed (a
    different one is warned about), so this can run again on every apply.
    Publish jobs of other shards, or ``compose``, may write it at once: the
    read-modify-write is done under the layout lock, and the file replaced
    atomically.
    """
    if count <= 0 or not os.path.isfile(path):
        return False
    with locked(layout_lock(path)):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if data.get("type") != "layout":
            logger.warning(f"Not a layout file, partition count not recorded: {path}")
            return False
        entry = _find_shard((data.get("data") or {}).get("map") or {}, shard)
        if entry is None:
            logger.warning(f"'{shard}' is not in the layout {path}: partition count not recorded")
            return False
        recorded = int(entry.get("partition_count") or 0)
        if recorded:
            if recorded != count:
                logger.warning(
                    f"The layout records {recorded} partitions for '{shard}', "
                    f"it is published with {count}: layout left unchanged"
                )
            return False
        entry["partition_count"] = count
        replace_atomically(path, yaml.dump(data, default_flow_style=False, sort_keys=True))
    logger.info(f"  └── Layout: '{shard}' published with {count} partitions")
    return True

