from email.mime.text import MIMEText

from pykmhelpers.core.wrapper import Wrapper


class MailNotifier(Wrapper):
    def __init__(self, dry_run: bool = False) -> None:
        super().__init__("/usr/sbin/sendmail", dry_run)

    def send(self, to: str, subject: str, body: str, sender: str = "") -> None:
        msg = MIMEText(body)
        msg["To"] = to
        msg["Subject"] = subject
        if sender:
            msg["From"] = sender

        cmd = [
            self.main_cmd,
            "-t",
            "-f",
            sender,
        ]

        self._run_byte_cmd(cmd, msg.as_bytes())


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Send an email via sendmail.")
    parser.add_argument("recipient")
    parser.add_argument("-s", "--subject", default="(no subject)")
    parser.add_argument("-f", "--from", dest="sender", default="")
    parser.add_argument("body", nargs="?", default="")
    args = parser.parse_args()

    body = args.body or sys.stdin.read()

    mail = MailNotifier(False)
    mail.send(args.recipient, args.subject, body, args.sender)
