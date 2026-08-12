"""
routes/auth.py -- /auth endpoints (AUTH-01).

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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

import user_service as svc
from dependencies import get_current_user
from security import create_access_token, verify_password
from user_models import MeResponse, Token, User

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