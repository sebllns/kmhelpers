import logging
import os

logger = logging.getLogger(__name__)


class ScriptRecorder:
    """Collects build/merge commands into a replayable shell script."""

    FILE_NAME = "kmhelpers_apply.sh"

    def __init__(self, workdir: str) -> None:
        self._workdir = workdir
        self._lines = [
            "#!/usr/bin/bash",
            f"WORKDIR='{workdir}'",
            "cd ${WORKDIR}",
        ]

    def add(self, cmd: str) -> None:
        self._lines.append(cmd.replace(self._workdir, "${WORKDIR}"))

    def write(self, directory: str) -> None:
        """Write the script to ``directory``, backing up any previous one as ``.bak``."""
        script_path = os.path.join(directory, self.FILE_NAME)
        if os.path.exists(script_path):
            backup_path = script_path + ".bak"
            os.replace(script_path, backup_path)
            logger.debug(f"Backed up existing script to {backup_path}")
        with open(script_path, "w") as f:
            f.write("\n".join(self._lines) + "\n")
        logger.info(f"Script written to {script_path}")
