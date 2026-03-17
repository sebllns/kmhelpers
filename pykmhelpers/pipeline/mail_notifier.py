import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pykmhelpers.core.wrapper import Wrapper


class MailNotifier(Wrapper):
    def __init__(self, dry_run: bool = False) -> None:
        super().__init__("/usr/sbin/sendmail", dry_run)

    def send(self, to: str, subject: str, body: str, sender: str = "", attachments: list[str] = []) -> None:
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject
        if sender:
            msg["From"] = sender

        msg.attach(MIMEText(body))

        for path in attachments:
            part = MIMEBase("application", "octet-stream")
            with open(path, "rb") as f:
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(path)}")
            msg.attach(part)

        cmd = [self.main_cmd, "-t", "-f", sender]
        self._run_byte_cmd(cmd, msg.as_bytes())


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Send an email via sendmail.")
    parser.add_argument("recipient")
    parser.add_argument("-s", "--subject", default="(no subject)")
    parser.add_argument("-f", "--from", dest="sender", default="")
    parser.add_argument("body", nargs="?", default="")
    parser.add_argument("-a", "--attachment", dest="attachments", action="append", default=[], metavar="FILE")
    args = parser.parse_args()

    body = args.body or sys.stdin.read()

    mail = MailNotifier(False)
    mail.send(args.recipient, args.subject, body, args.sender, args.attachments)
