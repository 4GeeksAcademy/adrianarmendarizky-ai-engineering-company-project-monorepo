"""
email_service.py -- sends transactional email via Resend (AUTH-03).

Kept in its own small module for one reason: forgot-password has to
return 200 no matter what happens here -- an invalid email, a Resend
outage, a bad API key -- none of that should ever surface to the
caller (that would leak information, or just be a confusing 500 for
something the user did nothing wrong to cause). So this function
swallows its own errors and logs them, rather than raising.
"""

import logging
import os

import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")

# onboarding@resend.dev works without verifying a domain -- but Resend
# restricts it to only deliver to the email address your own Resend
# account is registered with. Fine for this exercise; a verified
# domain would be required to send to arbitrary recipients for real.
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    try:
        resend.Emails.send(
            {
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": "Reset your Brasaland password",
                "text": (
                    "We received a request to reset your Brasaland account "
                    "password.\n\n"
                    f"Reset it here: {reset_url}\n\n"
                    "This link expires soon and can only be used once. If "
                    "you didn't request this, you can safely ignore this "
                    "email."
                ),
            }
        )
    except Exception:
        # Logged for us to debug, never raised -- see module docstring.
        logger.exception("Failed to send password reset email to %s", to_email)