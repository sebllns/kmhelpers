import logging
import os

logger = logging.getLogger(__name__)


def _echo(msg: str) -> str:
    return f"echo \"$(date '+%F %T') {msg}\""


class ScriptRecorder:
    """Collects build/merge commands into replayable shell scripts.

    Commands are grouped per script (one per shard, see ``WorkPlan.scripts``),
    builds and merges apart (``<shard>.sh``, ``<shard>_merge.sh``); ``write``
    emits one script per group and a runner calling them in order.
    """

    RUNNER_NAME = "kmhelpers_apply.sh"
    MERGE_SUFFIX = "_merge"

    def __init__(self, workdir: str) -> None:
        self._workdir = workdir
        self._groups: dict[str, list[str]] = {}
        self._current: str | None = None

    @property
    def current(self) -> str | None:
        """Script receiving the next commands."""
        return self._current

    @classmethod
    def merge_group(cls, name: str) -> str:
        """Script holding the merges of group ``name``.

        Merges go to their own script, run after the group's builds, so that
        they can wait for builds done elsewhere (e.g. a SLURM array).
        """
        return name if name.endswith(cls.MERGE_SUFFIX) else name + cls.MERGE_SUFFIX

    def select(self, name: str) -> None:
        """Make ``name`` the script receiving the next commands."""
        self._groups.setdefault(name, [])
        self._current = name

    def add(self, cmd: str, label: str) -> None:
        """Append ``cmd`` to the selected script, preceded by a timestamped ``label``."""
        if self._current is None:
            raise RuntimeError("No script selected")
        lines = self._groups[self._current]
        lines.append(_echo(f"[{self._current}] {label}"))
        lines.append(cmd.replace(self._workdir, "${WORKDIR}"))

    def write(self, directory: str) -> None:
        """Write the group scripts and the runner to ``directory``.

        Existing files are backed up with a ``.bak`` suffix.
        """
        os.makedirs(directory, exist_ok=True)
        runner: list[str] = []
        for name, lines in self._groups.items():
            self._write_file(directory, f"{name}.sh", lines + [_echo(f"[{name}] done")])
            runner += self._run_lines(os.path.join(directory, f"{name}.sh"))
        self._write_file(directory, self.RUNNER_NAME, runner)

    def _run_lines(self, script_path: str) -> list[str]:
        path = script_path.replace(self._workdir, "${WORKDIR}")
        shown = os.path.relpath(script_path, self._workdir)
        return [_echo(f"Running {shown}"), f'bash "{path}"']

    def _write_file(self, directory: str, file_name: str, lines: list[str]) -> None:
        path = os.path.join(directory, file_name)
        if os.path.exists(path):
            os.replace(path, path + ".bak")
            logger.debug(f"Backed up existing script to {path}.bak")
        # Stop at the first failure, so cleanup only runs after a successful merge
        header = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            # sizing assumes the hard open-files limit
            'ulimit -Sn "$(ulimit -Hn)" 2>/dev/null || true',
            # exported: commands run by a child shell (flock -c) use it too
            f"export WORKDIR='{self._workdir}'",
            "cd ${WORKDIR}",
        ]
        with open(path, "w") as f:
            f.write("\n".join(header + lines) + "\n")
        logger.info(f"Script written to {path}")
