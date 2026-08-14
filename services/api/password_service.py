"""
password_service.py -- business logic for password reset and change
(AUTH-03).

Same pattern as user_service.py: routes stay thin and call these
functions, which raise plain exceptions that the route layer turns
into HTTP status codes.
"""

import os
from datetime import datetime, timedelta, timezone

from tinydb import Query as TinyDBQuery

from database import password_resets_table, users_table
from security import (
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from user_service import get_user_by_email, get_user_by_id

ResetField = TinyDBQuery()

RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))


class InvalidResetTokenError(Exception):
    """Covers all three rejection cases the brief asks for -- unknown,
    expired, and already-used -- since a route shouldn't distinguish
    between them in its response (that would leak details an attacker
    could use)."""
    pass


class WrongPasswordError(Exception):
    pass


def create_password_reset(email: str) -> str | None:
    """If the email belongs to a real user, creates a reset record and
    returns the RAW token (the only place it ever exists outside the
    email itself -- the database only ever gets its hash). Returns
    None if there's no matching user -- the route still returns 200
    either way, it just skips sending an email."""
    user = get_user_by_email(email)
    if user is None:
        return None

    raw_token = generate_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=RESET_TOKEN_EXPIRE_MINUTES
    )
    password_resets_table.insert(
        {
            "user_id": user.id,
            "token_hash": hash_reset_token(raw_token),
            "expires_at": expires_at.isoformat(),
            "used": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return raw_token


def _invalidate_pending_resets(user_id: int) -> None:
    """Marks every not-yet-used reset record for this user as used.
    Called once a password actually changes (via reset OR via
    change-password) -- an old, still-unused reset link from three
    days ago shouldn't keep working after the person already changed
    their password some other way."""
    password_resets_table.update(
        {"used": True},
        (ResetField.user_id == user_id) & (ResetField.used == False),  # noqa: E712
    )


def consume_password_reset(raw_token: str, new_password: str) -> None:
    """Validates a reset token (exists, unexpired, unused) and, if
    valid, updates the password and marks the token used. Raises
    InvalidResetTokenError for any failure -- same response either
    way, on purpose."""
    token_hash = hash_reset_token(raw_token)
    record = password_resets_table.get(ResetField.token_hash == token_hash)

    if record is None or record["used"]:
        raise InvalidResetTokenError("Token is invalid or already used")

    expires_at = datetime.fromisoformat(record["expires_at"])
    if datetime.now(timezone.utc) >= expires_at:
        raise InvalidResetTokenError("Token has expired")

    users_table.update(
        {"hashed_password": hash_password(new_password)},
        doc_ids=[record["user_id"]],
    )
    password_resets_table.update({"used": True}, doc_ids=[record.doc_id])
    _invalidate_pending_resets(record["user_id"])


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    """Used by the authenticated /auth/change-password route -- the
    caller already knows *who* they are (via their session token);
    this only has to confirm they actually know their current
    password before letting them set a new one."""
    user = get_user_by_id(user_id)
    if user is None or not verify_password(current_password, user.hashed_password):
        raise WrongPasswordError("Current password is incorrect")

    users_table.update(
        {"hashed_password": hash_password(new_password)},
        doc_ids=[user_id],
    )
    _invalidate_pending_resets(user_id)