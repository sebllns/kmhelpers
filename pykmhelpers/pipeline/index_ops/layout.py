import logging
import os
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class LayoutStore:
    """Read/write access to the layout of the index being built.

    The layout holds what must stay identical across sessions, since indexes
    can only be merged when they share it: the partition count of each span
    and the minimizer size. Values missing from it are resolved on the first
    run and written back.

    Without a layout file (an index definition passed directly, or an older
    index), every getter returns ``None`` and saving does nothing.
    """

    def __init__(self, path: Optional[str]) -> None:
        self._path = path
        self._data: dict = {}
        self._dirty = False
        if path and os.path.isfile(path):
            with open(path) as f:
                loaded = yaml.safe_load(f) or {}
            if loaded.get("type") == "layout":
                self._data = loaded
            else:
                logger.warning(f"Not a layout file, ignored: {path}")

    @classmethod
    def next_to(cls, input_file: str) -> "LayoutStore":
        """Locate the layout of ``COMPOSE_DIR/NAME/SESSION/<file>.yaml``.

        `compose` writes it as ``COMPOSE_DIR/NAME_layout.yaml``.
        """
        session_dir = os.path.dirname(os.path.realpath(input_file))
        name_dir = os.path.dirname(session_dir)
        compose_dir = os.path.dirname(name_dir)
        name = os.path.basename(name_dir)
        if not name:
            return cls(None)
        return cls(os.path.join(compose_dir, f"{name}_layout.yaml"))

    @property
    def exists(self) -> bool:
        return bool(self._data)

    def minim_size(self) -> Optional[int]:
        return self._get(self._payload(), "minim_size")

    def set_minim_size(self, value: int) -> None:
        payload = self._payload()
        if payload is None:
            return
        payload["minim_size"] = value
        self._dirty = True

    def partition_count(self, span: int) -> Optional[int]:
        return self._get(self._span(span), "partition_count")

    def set_partition_count(self, span: int, value: int) -> None:
        entry = self._span(span)
        if entry is None:
            return
        entry["partition_count"] = value
        self._dirty = True

    def sample_budget(self, span: int) -> Optional[int]:
        """Samples the partition count should be sized for.

        The shard capacity when sharding is on, else what the span holds.
        """
        return self._get(self._span(span), "max_samples") or self._get(
            self._span(span), "total_samples"
        )

    def save(self) -> None:
        if not (self._dirty and self._path and self._data):
            return
        with open(self._path, "w") as f:
            yaml.dump(self._data, f, default_flow_style=False, sort_keys=True)
        self._dirty = False
        logger.debug(f"Updated layout: {self._path}")

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
