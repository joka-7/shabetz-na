"""Email to staff. Kept behind one small function so tests can replace it."""

from __future__ import annotations

import smtplib
from collections.abc import Sequence
from email.message import EmailMessage

from ..config import Settings


def send_email(settings: Settings, recipients: Sequence[str], subject: str, body: str) -> int:
    """Send one message to each recipient separately; returns how many were sent.

    Separate messages, so nobody sees anybody else's address. Does nothing
    when no mail server is configured.
    """
    if not settings.email_enabled or not recipients:
        return 0
    sent = 0
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        for address in recipients:
            message = EmailMessage()
            message["From"] = settings.smtp_from
            message["To"] = address
            message["Subject"] = subject
            message.set_content(body)
            server.send_message(message)
            sent += 1
    return sent
