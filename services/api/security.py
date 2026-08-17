"""
security.py -- password hashing and JWT helpers for AUTH-01.

Two unrelated concerns share this file because both are "low-level
crypto plumbing" that the rest of the app shouldn't need to think
about -- routes just call hash_password() or create_access_token()
and trust the result.

  1. Password hashing (passlib + bcrypt): turns a plaintext password
     into a one-way hash. There's no "unhash" -- to check a login, we
     hash the attempt again and compare hashes, never the raw text.

  2. JWT create/decode (python-jose): a JWT is a small signed JSON
     payload. "Signed" means anyone can read it, but only someone who
     knows SECRET_KEY could have produced a valid signature for it --
     so if decode succeeds, we know the token wasn't forged or edited.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

# --- Password hashing -------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT ----------------------------------------------------------------

# Read from the environment (populated from .env via load_dotenv() in
# main.py). If missing, fail fast during startup so the app never runs
# with an unsafe implicit secret.
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is required.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


def create_access_token(user_id: int) -> str:
    """Builds a token whose payload identifies the user (`sub`) and
    carries an expiry (`exp`). jose reads `exp` automatically and will
    raise on decode once it's passed."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Returns the decoded payload if the token is valid and unexpired.
    Raises jose.JWTError otherwise -- callers (get_current_user) turn
    that into a 401."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# --- Password reset tokens (AUTH-03) ---------------------------------

# Deliberately NOT a JWT. A JWT's `exp` claim only proves a token hasn't
# expired -- it says nothing about whether it's already been used, and
# there's no way to revoke one early without extra server-side state
# anyway. So instead: a random opaque string, sent to the user once by
# email, with only its *hash* ever stored here -- exactly like a
# password. Storing the hash (not the raw token) means a leaked
# password_resets table would still be useless to an attacker.

def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_reset_token(raw_token: str) -> str:
    """A fast, deterministic hash (not bcrypt) -- resetting a password
    means looking a token up by its hash, and bcrypt's per-call random
    salt makes that kind of direct lookup impossible. Bcrypt's slowness
    exists to slow down guessing a *short, human-chosen* password;
    these tokens are 32 random bytes, already unguessable, so that
    property buys nothing here."""
    return hashlib.sha256(raw_token.encode()).hexdigest()