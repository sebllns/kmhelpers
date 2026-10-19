import logging
import os
from typing import Optional

import yaml

from pykmhelpers.pipeline.composer import LAYOUT_FILE
from pykmhelpers.pipeline.index_ops.sources import session_dir_of

logger = logging.getLogger(__name__)


class LayoutStore:
    """Read-only access to the layout of the index being built.

    The layout is written by ``compose`` only: plan/apply/build never modify
    the design. It holds the minimizer size, the partition count of each span
    when the design fixes it (``-p``), the shard capacity and the chunk model
    of each span.

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
    def exists(self) -> bool:
        return bool(self._data)

    def minim_size(self) -> Optional[int]:
        return self._get(self._payload(), "minim_size")

    def partition_count(self, span: int) -> Optional[int]:
        return self._get(self._span(span), "partition_count")

    def sample_budget(self, span: int) -> Optional[int]:
        """Samples the partition count should be sized for.

        The shard capacity when sharding is on, else what the span holds.
        """
        return self._get(self._span(span), "max_samples") or self._get(
            self._span(span), "total_samples"
        )

    def chunk_samples(self, span: int) -> Optional[int]:
        """Most samples one kmtricks chunk of ``span`` holds (chunk model)."""
        return self._get(self._span(span), "chunk_samples")

    # ---

    def _payload(self) -> Optional[dict]:
        return self._data.get("data") if self._data else None

    def _span(self, span: int) -> Optional[dict]:
        payload = self._payload()
        entry = (payload or {}).get("map", {}).get(span)
        # A span mapped to a plain name predates these fields
        return entry if isinstance(entry, dict) else None

    @staticmethod
    def _get(entry: Optional[dict], key: str) -> Optional[int]:
        value = (entry or {}).get(key)
        return int(value) if value else None
