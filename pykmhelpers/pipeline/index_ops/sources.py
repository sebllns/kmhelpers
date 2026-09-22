import logging
import os
from dataclasses import dataclass, field

from pykmhelpers.core.log import Log
from pykmhelpers.pipeline.index_db import (
    IndexDB,
    IndexDefinition,
    IndexDefinitionTools,
    SerializedDataType,
)
from pykmhelpers.pipeline.index_ops.types import ApplyInputType, IndexOpsConfig

logger = logging.getLogger(__name__)


class DbCache:
    """Definition files loaded so far, keyed by absolute path."""

    def __init__(self) -> None:
        self._dbs: dict[str, list[IndexDB]] = {}

    def load(self, path: str, idt: IndexDefinitionTools) -> list[IndexDB]:
        if path not in self._dbs:
            self._dbs[path] = idt.load_db(path)
        return self._dbs[path]

    def source_dir(self, db: IndexDB | None) -> str | None:
        """Directory of the file ``db`` was loaded from."""
        for path, dbs in self._dbs.items():
            if db in dbs:
                return os.path.dirname(path)
        return None


@dataclass
class WorkPlan:
    """What a run has to do: definitions to build, then merges to perform.

    ``definitions`` is already filtered by name and span.
    """

    definitions: list[IndexDefinition] = field(default_factory=list)
    merges: dict[str, list[str]] = field(default_factory=dict)


def detect_input(
    path: str, idt: IndexDefinitionTools
) -> tuple[ApplyInputType, dict | None]:
    """Deserialize ``path`` and detect its input type.

    Returns ``(UNKNOWN, None)`` when the file is missing, unsupported or
    unparsable.
    """
    if not (os.path.isfile(path) and path.endswith((".yaml", ".yml", ".json"))):
        return ApplyInputType.UNKNOWN, None
    try:
        data = dict(idt.deserialize(path))
    except Exception as e:
        Log.handle_exception(
            logger=logger, msg=f"Could not parse schema from {path}", e=e
        )
        return ApplyInputType.UNKNOWN, None

    type_value = data.get("type") if data else None
    if type_value == SerializedDataType.INDEX_DEFINITION.value:
        return ApplyInputType.INDEX_DEFINITION, data
    if type_value == SerializedDataType.SPAN_DEFINITION.value:
        return ApplyInputType.SPAN_REGISTRY, data
    return ApplyInputType.UNKNOWN, data


def _named(dbs: list[IndexDB]) -> list[IndexDefinition]:
    return [i for db in dbs for i in db.index_table.values() if i.name]


class IndexDefinitionSource:
    """Index definition file: build every selected definition, no merge."""

    def __init__(self, config: IndexOpsConfig, cache: DbCache) -> None:
        self._config = config
        self._cache = cache

    def load(self, path: str, idt: IndexDefinitionTools, data: dict) -> WorkPlan:
        return WorkPlan(
            definitions=[
                i for i in _named(self._cache.load(path, idt)) if self._selected(i)
            ]
        )

    def _selected(self, i: IndexDefinition) -> bool:
        names, spans = self._config.filter_names, self._config.filter_spans
        return (names is None or i.name in names) and (spans is None or i.span in spans)


class SpanRegistrySource:
    """Span registry: build the parts of each selected merge target, then merge them.

    The registry maps each span to ``{"indices": {target: [part, ...]}}``.
    Each part is described by a sibling definition file named after it.
    """

    def __init__(self, config: IndexOpsConfig, cache: DbCache) -> None:
        self._config = config
        self._cache = cache

    def load(self, path: str, idt: IndexDefinitionTools, data: dict) -> WorkPlan:
        names = self._config.filter_names
        spans = self._config.filter_spans
        dbs: list[IndexDB] = []
        merges: dict[str, list[str]] = {}

        for span, entry in dict[int, dict](data["data"]).items():
            if spans and span not in spans:
                continue
            indices = entry.get("indices")
            if not indices:
                raise ValueError("Span registry is missing field 'indices'")
            for target, parts in dict[str, list[str]](indices).items():
                if not names or target in names:
                    merges[target] = parts
                # A part is built when its target is selected, or when it is selected itself
                for part in parts:
                    if target in merges or (names and part in names):
                        dbs.extend(self._cache.load(self._part_path(path, part), idt))

        return WorkPlan(definitions=_named(dbs), merges=merges)

    @staticmethod
    def _part_path(registry_path: str, part: str) -> str:
        db_path = os.path.join(
            os.path.dirname(registry_path), part + os.path.splitext(registry_path)[1]
        )
        if not os.path.isfile(db_path):
            raise FileNotFoundError(f"Could not find required data file at {db_path}")
        return db_path


SOURCES: dict[
    ApplyInputType, type[IndexDefinitionSource] | type[SpanRegistrySource]
] = {
    ApplyInputType.INDEX_DEFINITION: IndexDefinitionSource,
    ApplyInputType.SPAN_REGISTRY: SpanRegistrySource,
}
