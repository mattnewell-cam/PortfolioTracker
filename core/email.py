import logging
from typing import Iterable

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SENDINBLUE_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def send_email(sender: str, subject: str, message: str, recipient_list: Iterable[str], fail_silently: bool = True):
    recipients = [r for r in recipient_list if r]
    if not recipients:
        return False

    api_key = getattr(settings, "EMAIL_API_KEY", "")
    if not api_key:
        msg = "EMAIL_API_KEY is not configured; skipping email send."
        print(msg)
        if fail_silently:
            logger.warning(msg)
            return False
        raise ValueError(msg)

    payload = {
        "sender": {"email": settings.EMAIL_SENDER},
        "to": [{"email": email} for email in recipients],
        "subject": subject,
        "textContent": message,
    }
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            SENDINBLUE_ENDPOINT, json=payload, headers=headers, timeout=5
        )
        if response.status_code >= 400:
            logger.error(
                "Email send failed with status %s: %s",
                response.status_code,
                response.text,
            )
            if not fail_silently:
                response.raise_for_status()
            return False
        return True
    except Exception:
        logger.exception("Email send failed")
        if not fail_silently:
            raise
        return False
