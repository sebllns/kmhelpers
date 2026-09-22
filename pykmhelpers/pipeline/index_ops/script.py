import logging
import os
import re

logger = logging.getLogger(__name__)


def script_name(index_name: str) -> str:
    """Script of an index: its name without the ``_p<n>`` part suffix.

    Parts of one merge target share this prefix (``{db}_g{span}_{session}``).
    """
    return re.sub(r"_p\d+$", "", index_name)


class ScriptRecorder:
    """Collects build/merge commands into replayable shell scripts.

    Commands are grouped per script (see ``script_name``); ``write`` emits one
    script per group and a runner script calling them in order.
    """

    RUNNER_NAME = "kmhelpers_apply.sh"

    def __init__(self, workdir: str) -> None:
        self._workdir = workdir
        self._groups: dict[str, list[str]] = {}
        self._current: list[str] | None = None

    def select(self, name: str) -> None:
        """Make ``name`` the script receiving the next commands."""
        self._current = self._groups.setdefault(name, [])

    def add(self, cmd: str) -> None:
        if self._current is None:
            raise RuntimeError("No script selected")
        self._current.append(cmd.replace(self._workdir, "${WORKDIR}"))

    def write(self, directory: str) -> None:
        """Write the group scripts and the runner to ``directory``.

        Existing files are backed up with a ``.bak`` suffix.
        """
        os.makedirs(directory, exist_ok=True)
        for name, lines in self._groups.items():
            self._write_file(directory, f"{name}.sh", lines)
        runner = [
            f'bash "{os.path.join(directory, name + ".sh")}"'.replace(
                self._workdir, "${WORKDIR}"
            )
            for name in self._groups
        ]
        self._write_file(directory, self.RUNNER_NAME, runner)

    def write_entry(self, directory: str, script_path: str) -> None:
        """Write ``<directory>/kmhelpers_apply.sh`` running ``script_path``."""
        cmd = f'bash "{script_path}"'.replace(self._workdir, "${WORKDIR}")
        self._write_file(directory, self.RUNNER_NAME, [cmd])

    def _write_file(self, directory: str, file_name: str, lines: list[str]) -> None:
        path = os.path.join(directory, file_name)
        if os.path.exists(path):
            os.replace(path, path + ".bak")
            logger.debug(f"Backed up existing script to {path}.bak")
        # set -e: stop at the first failure, so cleanup only runs after a successful merge
        header = [
            "#!/usr/bin/bash",
            "set -e",
            f"WORKDIR='{self._workdir}'",
            "cd ${WORKDIR}",
        ]
        with open(path, "w") as f:
            f.write("\n".join(header + lines) + "\n")
        logger.info(f"Script written to {path}")
