"""Email notification at exit, for the commands that run a plan (apply, build)."""

import atexit
import logging
import signal
import sys

import pykmhelpers.core.log
import pykmhelpers.pipeline.mail_notifier
from pykmhelpers.pipeline.index_ops import ApplyStatus

logger = logging.getLogger(__name__)

SENDER = "kmhelpers@groupes.renater.fr"


class ExitNotifier:
    """Mails ``recipient`` the final ``status`` of ``command`` when the process exits,
    also on SIGTERM (e.g. a SLURM job cancelled or out of time)."""

    def __init__(self, command: str, recipient: str | None) -> None:
        self.command = command
        self.recipient = recipient
        self.status = ApplyStatus.NONE.value
        self.log_dir = "UNDEFINED_LOG_DIR"
        self.attachments: list[str] = []
        if pykmhelpers.core.log.Log.log_file:
            self.attachments.append(pykmhelpers.core.log.Log.log_file)
        if recipient:
            atexit.register(self._send)
            signal.signal(signal.SIGTERM, self._on_sigterm)

    def _on_sigterm(self, sig, frame) -> None:
        self.status = ApplyStatus.NONE.value
        sys.exit(1)

    def _send(self) -> None:
        status = "CANCELLED" if self.status == ApplyStatus.NONE.value else self.status
        try:
            pykmhelpers.pipeline.mail_notifier.MailNotifier(dry_run=False).send(
                to=self.recipient,
                subject=f"[kmhelpers {self.command}] {status}",
                body=(
                    f"kmhelpers {self.command} exited with status: {status}\n"
                    f"logs can be found in {self.log_dir}"
                ),
                sender=SENDER,
                attachments=self.attachments,
            )
        except Exception as e:
            logger.warning(f"Could not send notification email: {e}")
