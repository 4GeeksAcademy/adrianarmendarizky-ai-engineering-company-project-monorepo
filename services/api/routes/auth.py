"""
routes/auth.py -- /auth endpoints (AUTH-01, extended in AUTH-03).

POST /auth/login is deliberately public -- it's how a client gets a
token in the first place. GET /auth/me requires one, via
get_current_user.

login() takes an OAuth2PasswordRequestForm instead of a JSON body on
purpose: it's the standard pairing with OAuth2PasswordBearer (the
scheme get_current_user uses), and it's what makes /docs' "Authorize"
button work without any manual copy-pasting -- click Authorize, enter
an email/password, and Swagger calls this route and attaches the
resulting token to every request automatically. The form's field is
called "username" (that's fixed by the OAuth2 spec), but we treat
whatever's in it as an email.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

import password_service as pwd_svc
import user_service as svc
from dependencies import get_current_user
from email_service import send_password_reset_email
from security import create_access_token, verify_password
from user_models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    MeResponse,
    ResetPasswordRequest,
    Token,
    User,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = svc.get_user_by_email(form_data.username)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        # Same error either way -- confirming "no such email" vs. "wrong
        # password" would tell an attacker which emails are registered.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(user_id=user.id)
    return Token(access_token=access_token)


@router.get("/me", response_model=MeResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    profile = svc.get_profile_by_user_id(current_user.id)
    return MeResponse(email=current_user.email, role=current_user.role, profile=profile)


# ---------------------------------------------------------------------------
# Password reset and change (AUTH-03). All three are under /auth, per the
# brief -- forgot/reset are public (that's the whole point), change requires
# a session.
# ---------------------------------------------------------------------------

# Base URL of whichever frontend hosts /reset-password (Backoffice) -- the
# backend has no way to know this on its own, so it has to be configured.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    raw_token = pwd_svc.create_password_reset(payload.email)
    if raw_token is not None:
        reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
        send_password_reset_email(payload.email, reset_url)

    # Same response whether the email exists or not, and even if sending
    # the email itself failed -- any of those leaking through would tell
    # an attacker something they shouldn't be able to learn.
    return {"detail": "If that address is registered, you'll receive a reset link shortly."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    try:
        pwd_svc.consume_password_reset(payload.token, payload.new_password)
    except pwd_svc.InvalidResetTokenError:
        raise HTTPException(status_code=400, detail="Invalid, expired, or already-used token")

    return {"detail": "Password updated"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest, current_user: User = Depends(get_current_user)
):
    try:
        pwd_svc.change_password(
            current_user.id, payload.current_password, payload.new_password
        )
    except pwd_svc.WrongPasswordError:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    return {"detail": "Password updated"}