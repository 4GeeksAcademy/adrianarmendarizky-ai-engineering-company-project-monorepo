"""
dependencies.py -- shared FastAPI dependencies (AUTH-01).

get_current_user is what makes route protection possible: any route
that declares it as a parameter has FastAPI run this function first,
on every request. If it raises, the route's own code never runs.
"""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

import user_service as svc
from security import decode_access_token
from user_models import User

# tokenUrl just tells the /docs page where a token comes from (so the
# "Authorize" button knows which endpoint to point at) -- it doesn't
# change how this dependency itself checks a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    unauthorized = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
    except JWTError:
        # Covers a malformed token, a bad signature, AND an expired
        # one -- jose raises the same JWTError family for all three.
        raise unauthorized

    user_id = payload.get("sub")
    if user_id is None:
        raise unauthorized

    user = svc.get_user_by_id(int(user_id))
    if user is None:
        # Token is validly signed, but the user it points to no longer
        # exists (e.g. deleted after the token was issued).
        raise unauthorized

    return user