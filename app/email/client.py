"""
Email client abstraction.
For the take-home we support two modes:

1. MOCK mode (default) – just prints / logs the email. Perfect for local demos.
2. Real SMTP mode – set SMTP_* environment variables.

Inbound is handled by the FastAPI webhook (or can be extended with IMAP).
"""

import os
import logging
from typing import Optional
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class EmailClient:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.from_addr = os.getenv("FROM_ADDRESS", "alex@marseer.ai")
        self.from_name = os.getenv("FROM_NAME", "Alex Rivera")
        self.mock = not all([self.smtp_host, self.smtp_user, self.smtp_pass])

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> bool:
        if self.mock:
            logger.info("=" * 60)
            logger.info("[MOCK EMAIL] To: %s", to)
            logger.info("[MOCK EMAIL] Subject: %s", subject)
            logger.info("[MOCK EMAIL] Body:\n%s", body)
            logger.info("=" * 60)
            print(f"\n----- MOCK EMAIL to {to} -----\nSubject: {subject}\n\n{body}\n-----------------------------\n")
            return True

        # Real SMTP path (requires aiosmtplib)
        try:
            import aiosmtplib
            msg = EmailMessage()
            msg["From"] = f"{self.from_name} <{self.from_addr}>"
            msg["To"] = to
            msg["Subject"] = subject
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                msg["References"] = in_reply_to
            msg.set_content(body)

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_pass,
                start_tls=True,
            )
            return True
        except Exception as e:
            logger.exception("Failed to send email: %s", e)
            return False


# Singleton for convenience
email_client = EmailClient()