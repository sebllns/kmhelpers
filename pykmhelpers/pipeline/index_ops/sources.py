import logging
import os
from dataclasses import dataclass, field

from pykmhelpers.core.log import Log
from pykmhelpers.core.utils import matches_any, unmatched_patterns
from pykmhelpers.pipeline.composer import (
    LAYOUT_FILE,
    SESSION_FILE,
    SHARDS_DIR,
    load_layout_sessions,
)
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

    ``definitions`` is already filtered by name. ``scripts`` maps an
    index name to the script it belongs to: parts go with the shard they are
    merged into, so one script builds one shard.
    """

    definitions: list[IndexDefinition] = field(default_factory=list)
    merges: dict[str, list[str]] = field(default_factory=dict)
    scripts: dict[str, str] = field(default_factory=dict)

    def script_of(self, name: str) -> str:
        return self.scripts.get(name, name)


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
    if type_value == SerializedDataType.INDEX_SESSION.value:
        return ApplyInputType.INDEX_SESSION, data
    return ApplyInputType.UNKNOWN, data


def _named(dbs: list[IndexDB]) -> list[IndexDefinition]:
    return [i for db in dbs for i in db.index_table.values() if i.name]


def _check_matched(patterns: list[str], names: list) -> None:
    """Refuse a --shard pattern that matches no shard: likely a typo."""
    missing = unmatched_patterns(names, patterns)
    if missing:
        raise ValueError(f"No shard matches {', '.join(missing)}")


class IndexDefinitionSource:
    """Index definition file: build every selected definition, no merge."""

    def __init__(self, config: IndexOpsConfig, cache: DbCache) -> None:
        self._config = config
        self._cache = cache

    def load(self, path: str, idt: IndexDefinitionTools, data: dict) -> WorkPlan:
        named = _named(self._cache.load(path, idt))
        patterns = self._config.filter_names
        if not patterns:
            return WorkPlan(definitions=named)
        _check_matched(patterns, [i.name for i in named])
        return WorkPlan(definitions=[i for i in named if matches_any(i.name, patterns)])


class IndexSessionSource:
    """Session file: build the parts of each selected shard, then merge them.

    ``SESSION/index.yaml`` maps each shard to ``{"span", "file", ...}``; the
    shard file (``shards/<shard>.yaml``) holds the parts this session adds to
    it, merged into the shard once built.
    """

    def __init__(self, config: IndexOpsConfig, cache: DbCache) -> None:
        self._config = config
        self._cache = cache

    def load(self, path: str, idt: IndexDefinitionTools, data: dict) -> WorkPlan:
        patterns = self._config.filter_names
        shards = data.get("shards")
        if not shards:
            raise ValueError(f"Session file has no 'shards': {path}")

        definitions: list[IndexDefinition] = []
        merges: dict[str, list[str]] = {}
        seen: list[str] = []
        for shard, entry in dict[str, dict](shards).items():
            parts = _named(self._cache.load(self._shard_path(path, entry), idt))
            seen += [shard] + [i.name for i in parts if i.name]
            # A shard is merged when selected; a part selected alone is only built
            if not patterns or matches_any(shard, patterns):
                merges[shard] = [i.name for i in parts if i.name]
                definitions.extend(parts)
            else:
                definitions.extend(
                    i for i in parts if i.name and matches_any(i.name, patterns)
                )
        if patterns:
            _check_matched(patterns, seen)

        scripts = {part: shard for shard, parts in merges.items() for part in parts}
        return WorkPlan(definitions=definitions, merges=merges, scripts=scripts)

    @staticmethod
    def _shard_path(session_path: str, entry: dict) -> str:
        if not entry.get("file"):
            raise ValueError(f"Shard entry without 'file' in {session_path}")
        shard_path = os.path.join(os.path.dirname(session_path), entry["file"])
        if not os.path.isfile(shard_path):
            raise FileNotFoundError(f"Could not find shard file at {shard_path}")
        return shard_path


SOURCES: dict[
    ApplyInputType, type[IndexDefinitionSource] | type[IndexSessionSource]
] = {
    ApplyInputType.INDEX_DEFINITION: IndexDefinitionSource,
    ApplyInputType.INDEX_SESSION: IndexSessionSource,
}


def session_dir_of(input_file: str) -> str:
    """Session directory of ``SESSION/index.yaml`` or ``SESSION/shards/<x>.yaml``."""
    directory = os.path.dirname(os.path.realpath(input_file))
    if os.path.basename(directory) == SHARDS_DIR:
        return os.path.dirname(directory)
    return directory


def _session_file(session_dir: str) -> str | None:
    for ext in ("yaml", "yml", "json"):
        path = os.path.join(session_dir, f"{SESSION_FILE}.{ext}")
        if os.path.isfile(path):
            return path
    return None


def resolve_input(path: str, session: str | None = None) -> str:
    """Definition file to plan, apply or build for ``path``.

    ``path`` can be a definition file (``SESSION/index.yaml``, or
    ``SESSION/shards/<shard>.yaml`` to build one shard without merge), a
    session directory, an index directory (``COMPOSE_DIR/NAME``, holding
    ``layout.yaml``), a compose directory or a design directory holding one
    index. In an index directory the session is ``session``, or else the last
    one composed.
    """
    if os.path.isfile(path):
        return path
    if not os.path.isdir(path):
        raise FileNotFoundError(f"No such file or directory: {path}")

    found = _session_file(path)
    if found:
        return found

    if os.path.isfile(os.path.join(path, LAYOUT_FILE)):
        return _resolve_session(path, session)

    compose_dir = path
    if os.path.isdir(os.path.join(path, "compose")):
        compose_dir = os.path.join(path, "compose")  # a design directory
    indexes = sorted(
        e.path
        for e in os.scandir(compose_dir)
        if e.is_dir() and os.path.isfile(os.path.join(e.path, LAYOUT_FILE))
    )
    if len(indexes) == 1:
        return _resolve_session(indexes[0], session)
    if not indexes:
        raise FileNotFoundError(f"No index found in {path}")
    raise ValueError(
        f"{path} holds several indexes ({', '.join(os.path.basename(i) for i in indexes)}): "
        f"pass one of them, e.g. {indexes[0]}"
    )


def _resolve_session(index_dir: str, session: str | None) -> str:
    sessions = load_layout_sessions(os.path.join(index_dir, LAYOUT_FILE))
    if session is None:
        if not sessions:
            raise ValueError(f"No session recorded in {index_dir}/{LAYOUT_FILE}")
        session = sessions[-1]
    found = _session_file(os.path.join(index_dir, session))
    if not found:
        known = ", ".join(sessions) or "none"
        raise FileNotFoundError(
            f"No session '{session}' in {index_dir} (sessions: {known})"
        )
    logger.info(f"Session '{session}' of {os.path.basename(index_dir)}: {found}")
    return found
