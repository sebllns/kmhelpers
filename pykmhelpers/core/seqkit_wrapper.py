"""SeqKitWrapper - thin wrapper around the seqkit binary for sequence checks."""

import logging
import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Union

from pykmhelpers.core.wrapper import Wrapper

logger = logging.getLogger(__name__)


class SeqKitWrapper(Wrapper):
    """
    Wrapper for seqkit (https://bioinf.shenwei.me/seqkit/).

    Construction raises FileNotFoundError when seqkit is not on PATH (or via
    the SEQKIT_BIN_PATH environment variable), so callers can try/except to
    detect availability and fall back.

    Example:
        >>> if SeqKitWrapper.is_available():
        ...     ok, errors = SeqKitWrapper().validate("reads.fastq.gz")
    """

    def __init__(self, dry_run: bool = False):
        super().__init__(main_cmd="seqkit", dry_run=dry_run)

    @classmethod
    def is_available(cls) -> bool:
        """Return True if the seqkit binary can be located."""
        try:
            cls()
            return True
        except FileNotFoundError:
            return False

    def validate(
        self, filepath: Union[str, Path], strict: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Validate a FASTA/FASTQ file with seqkit.

        Reading and re-emitting the file makes seqkit fail on structural
        problems. When `strict` is set, the sequence alphabet is additionally
        validated against DNA IUPAC (the more expensive part). The DNA type is
        pinned explicitly: seqkit's auto-guess is too lenient and lets stray
        characters pass.

        Returns:
            (is_valid, errors) where errors holds seqkit's stderr lines.
        """
        cmd = [self.main_cmd, "seq"]
        if strict:
            cmd += ["--validate-seq", "--seq-type", "dna"]
        cmd += ["-w", "0", "-o", os.devnull, str(filepath)]
        try:
            self._run_cmd(cmd, log_errors_only=True)
            return True, []
        except subprocess.SubprocessError as e:
            # _run_cmd embeds seqkit's stderr after a "Log:" marker; keep that
            # part when present, otherwise fall back to the full message.
            text = str(e)
            _, _, log = text.partition("Log:")
            payload = (log or text).strip()
            errors = [line.strip() for line in payload.splitlines() if line.strip()]
            return False, errors or [payload]