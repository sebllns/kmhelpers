import os
from dataclasses import dataclass

from pykmhelpers.pipeline.index_ops.sources import session_dir_of

# Folders of BUILD_DIR that are not registry entries
RESERVED_NAMES = frozenset({"work", "assets", "logs"})


def check_index_name(name: str) -> None:
    """Refuse names that would clash with the folders of ``BUILD_DIR``.

    Published indexes are directories of ``BUILD_DIR`` itself (the registry).
    """
    if name in RESERVED_NAMES or name.startswith(".") or os.sep in name:
        raise ValueError(
            f"'{name}' cannot be an index name: reserved for BUILD_DIR "
            f"({', '.join(sorted(RESERVED_NAMES))}, hidden or nested names)"
        )


@dataclass(frozen=True)
class BuildPaths:
    """Layout of one session in ``BUILD_DIR``, the only place paths are derived.

    ``BUILD_DIR`` is the kmindex registry. Published indexes live in it, in
    place (``BUILD_DIR/<name>``, a directory, not a symlink); everything
    temporary to a session is under ``work/<session>/``, on the same
    filesystem so that publishing is a rename::

        BUILD_DIR/
        ├── index.json
        ├── <name>/                    published index
        ├── work/<session>/
        │   ├── runs/<run>/            kmtricks runs (parts, chunks)
        │   ├── merges/<target>/<step>/  throwaway registry + merge output
        │   └── previous/<target>      replaced version, during an update
        ├── assets/<session>/          scripts, fofs, tsv
        └── logs/
    """

    build_dir: str
    session: str

    @classmethod
    def for_input(cls, build_dir: str, input_file: str) -> "BuildPaths":
        """Paths of the session of ``COMPOSE_DIR/NAME/SESSION/index.yaml`` (or of
        a shard file of the session)."""
        session = os.path.basename(session_dir_of(input_file))
        return cls(os.path.realpath(build_dir), session)

    @property
    def registry(self) -> str:
        return self.build_dir

    @property
    def lock(self) -> str:
        """Taken (``flock``) by every change of the registry."""
        return os.path.join(self.build_dir, ".registry.lock")

    @property
    def assets(self) -> str:
        return os.path.join(self.build_dir, "assets", self.session)

    @property
    def logs(self) -> str:
        return os.path.join(self.build_dir, "logs")

    @property
    def work(self) -> str:
        return os.path.join(self.build_dir, "work", self.session)

    @property
    def runs(self) -> str:
        return os.path.join(self.work, "runs")

    def shard(self, name: str) -> str:
        """Published index ``name``."""
        return os.path.join(self.build_dir, name)

    def run(self, name: str) -> str:
        return os.path.join(self.runs, name)

    def merges(self, target: str) -> str:
        return os.path.join(self.work, "merges", target)

    def merge_step(self, target: str, step: str) -> str:
        """Holds ``registry/`` (the step's inputs) and ``out/`` (its result)."""
        return os.path.join(self.merges(target), step)

    def previous(self, target: str) -> str:
        return os.path.join(self.work, "previous", target)
