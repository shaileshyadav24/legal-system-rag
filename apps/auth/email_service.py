"""Sends transactional emails via Resend."""
import logging

import resend
from fastapi import HTTPException, status

from libs.shared.config import PASSWORD_RESET_URL, RESEND_API_KEY, RESEND_FROM_EMAIL

logger = logging.getLogger(__name__)

resend.api_key = RESEND_API_KEY


def send_password_reset_email(to_email: str, reset_token: str, expires_in_minutes: int) -> None:
    reset_link = f"{PASSWORD_RESET_URL}?token={reset_token}"
    try:
        resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": "Reset your password",
            "html": (
                f"<p>We received a request to reset your password.</p>"
                f'<p><a href="{reset_link}">Click here to reset your password</a></p>'
                f"<p>This link expires in {expires_in_minutes} minutes. "
                f"If you didn't request this, you can safely ignore this email.</p>"
            ),
        })
    except resend.exceptions.ResendError as exc:
        logger.exception("Failed to send password reset email to %s", to_email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send password reset email",
        ) from exc
