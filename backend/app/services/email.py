import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("finguard.email")


class EmailSender(Protocol):
    def send_password_reset(self, to_email: str, reset_token: str) -> None: ...


class ConsoleEmailSender:
    def send_password_reset(self, to_email: str, reset_token: str) -> None:
        logger.info("DEV password reset email queued for %s (token length=%d)", to_email, len(reset_token))


class SMTPEmailSender:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send_password_reset(self, to_email: str, reset_token: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = "FinGuard Password Reset"
        msg["From"] = self.sender
        msg["To"] = to_email
        msg.set_content(f"Use this token to reset your FinGuard password: {reset_token}")
        with smtplib.SMTP(self.host, self.port, timeout=5) as smtp:
            smtp.ehlo()
            if self.use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)


def get_email_sender() -> EmailSender:
    backend = os.getenv("FINGUARD_EMAIL_BACKEND", "console").lower()
    if backend in ("smtp", "mailpit"):
        host = os.getenv("FINGUARD_SMTP_HOST", "localhost")
        port = int(os.getenv("FINGUARD_SMTP_PORT", "1025" if backend == "mailpit" else "587"))
        sender = os.getenv("FINGUARD_SMTP_FROM", "no-reply@finguard.local")
        is_prod = os.getenv("FINGUARD_ENV", "development").lower() == "production"
        default_tls = "0" if (backend == "mailpit" or port == 1025) and not is_prod else "1"
        use_tls = True if is_prod else os.getenv("FINGUARD_SMTP_STARTTLS", default_tls).lower() in ("1", "true", "yes")
        return SMTPEmailSender(
            host=host,
            port=port,
            sender=sender,
            username=os.getenv("FINGUARD_SMTP_USER", ""),
            password=os.getenv("FINGUARD_SMTP_PASSWORD", ""),
            use_tls=use_tls,
        )
    return ConsoleEmailSender()
