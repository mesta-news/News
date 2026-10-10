"""Optional e-mail delivery of the digest via SMTP (e.g. a Gmail app password)."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import date
from email.message import EmailMessage

log = logging.getLogger(__name__)


def send_email(html_body: str, url: str = "") -> None:
    host, user, password, to = (os.environ.get(k) for k in
                                ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_EMAIL_TO"))
    if not all((host, user, password, to)):
        log.info("SMTP_HOST/SMTP_USER/SMTP_PASSWORD/DIGEST_EMAIL_TO not all set - not emailing")
        return
    msg = EmailMessage()
    msg["Subject"] = f"Daily Digest - {date.today():%a %d %b %Y}"
    msg["From"] = user
    msg["To"] = to  # comma-separated list is fine
    msg.set_content(f"Your daily digest is ready: {url or '(open the HTML version)'}")
    msg.add_alternative(html_body, subtype="html")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    log.info("digest emailed to %s", to)
