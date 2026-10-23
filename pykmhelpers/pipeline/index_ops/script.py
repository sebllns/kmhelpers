import logging
import os

logger = logging.getLogger(__name__)

MERGE_SCRIPT = "merge"


def _echo(msg: str) -> str:
    return f"echo \"$(date '+%F %T') {msg}\""


class ScriptRecorder:
    """Collects build/merge commands into replayable shell scripts.

    Commands are grouped per script, named ``<task dir>/<name>``: one script
    per kmtricks run (``<dir>/<run>.sh``) and one for the merge of the task
    (``<dir>/merge.sh``, see ``merge_group``). ``write`` emits one script per
    group under the session's assets folder.
    """

    def __init__(self, workdir: str) -> None:
        self._workdir = workdir
        self._groups: dict[str, list[str]] = {}
        self._current: str | None = None

    @property
    def current(self) -> str | None:
        """Script receiving the next commands."""
        return self._current

    @property
    def groups(self) -> list[str]:
        """Scripts recorded so far, in recording order."""
        return list(self._groups)

    @staticmethod
    def merge_group(task_dir: str) -> str:
        """Script holding the merge of the task written to ``task_dir``.

        The merge has its own script, run after the builds of the task, so
        that it can wait for builds done elsewhere (e.g. a SLURM array).
        """
        return f"{task_dir}/{MERGE_SCRIPT}"

    def select(self, name: str) -> None:
        """Make ``name`` the script receiving the next commands."""
        self._groups.setdefault(name, [])
        self._current = name

    def add(self, cmd: str, label: str) -> None:
        """Append ``cmd`` to the selected script, preceded by a timestamped ``label``."""
        if self._current is None:
            raise RuntimeError("No script selected")
        lines = self._groups[self._current]
        tag = os.path.basename(self._current)
        lines.append(_echo(f"[{tag}] {label}"))
        lines.append(cmd.replace(self._workdir, "${WORKDIR}"))

    def write(self, directory: str) -> list[str]:
        """Write one script per group under ``directory``; return their paths."""
        written = []
        for name, lines in self._groups.items():
            tag = os.path.basename(name)
            path = os.path.join(directory, f"{name}.sh")
            self._write_file(path, lines + [_echo(f"[{tag}] done")])
            written.append(path)
        return written

    def _write_file(self, path: str, lines: list[str]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
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
        os.chmod(path, 0o755)
        logger.debug(f"Script written to {path}")
