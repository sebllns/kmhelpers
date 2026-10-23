"""Email notifications of the commands that run a plan (apply, build).

``--notify EMAIL`` mails the end of the build; ``--notify-level shard`` also
mails the end of each shard. The mails carry the progress tree of the build
(``status.render``).
"""

import atexit
import logging
import os
import signal
import sys
from typing import Callable, Optional

import pykmhelpers.core.log
import pykmhelpers.pipeline.mail_notifier
from pykmhelpers.pipeline.index_ops import ApplyStatus

logger = logging.getLogger(__name__)

SENDER = "kmhelpers@groupes.renater.fr"
GLOBAL = "global"
SHARD = "shard"
LEVELS = (GLOBAL, SHARD)


def mail(to: str, subject: str, body: str, attachments: Optional[list[str]] = None) -> None:
    """Send one mail; a failure is logged, never raised."""
    try:
        pykmhelpers.pipeline.mail_notifier.MailNotifier(dry_run=False).send(
            to=to,
            subject=subject,
            body=body,
            sender=SENDER,
            attachments=[a for a in attachments or [] if a and os.path.isfile(a)],
        )
        logger.info(f"Notification sent to {to}: {subject}")
    except Exception as e:
        logger.warning(f"Could not send notification email: {e}")


class ExitNotifier:
    """Mails ``recipient`` the final status of ``command`` when the process exits,
    also on SIGTERM (e.g. a SLURM job cancelled or out of time).

    ``level`` ``shard`` also mails each shard when it ends (``shard_end``).
    ``final=False`` keeps only the shard mails (a SLURM job ending one shard:
    the end of the build is mailed by its last job). ``progress`` returns the
    progress tree as text, put in the mails.
    """

    def __init__(
        self,
        command: str,
        recipient: Optional[str],
        level: str = GLOBAL,
        final: bool = True,
    ) -> None:
        self.command = command
        self.recipient = recipient
        self.level = level
        self.status = ApplyStatus.NONE.value
        self.log_dir = "UNDEFINED_LOG_DIR"
        self.attachments: list[str] = []
        self.progress: Optional[Callable[[Optional[list[str]]], str]] = None
        if pykmhelpers.core.log.Log.log_file:
            self.attachments.append(pykmhelpers.core.log.Log.log_file)
        if recipient and final:
            atexit.register(self._send)
            signal.signal(signal.SIGTERM, self._on_sigterm)

    def _on_sigterm(self, sig, frame) -> None:
        self.status = ApplyStatus.NONE.value
        sys.exit(1)

    def _body(self, shards: Optional[list[str]] = None) -> str:
        if not self.progress:
            return ""
        try:
            return self.progress(shards)
        except Exception as e:
            return f"(progress not available: {e})"

    def shard_end(self, shard: str, status: str) -> None:
        """With level ``shard``, mail the end of ``shard``."""
        if not (self.recipient and self.level == SHARD):
            return
        mail(
            self.recipient,
            f"[kmhelpers {self.command}] {shard} {status}",
            self._body([shard]) + f"\n\nlogs can be found in {self.log_dir}",
            self.attachments,
        )

    def _send(self) -> None:
        status = "CANCELLED" if self.status == ApplyStatus.NONE.value else self.status
        body = f"kmhelpers {self.command} exited with status: {status}\n"
        progress = self._body()
        if progress:
            body += f"\n{progress}\n"
        body += f"\nlogs can be found in {self.log_dir}"
        mail(self.recipient, f"[kmhelpers {self.command}] {status}", body, self.attachments)
