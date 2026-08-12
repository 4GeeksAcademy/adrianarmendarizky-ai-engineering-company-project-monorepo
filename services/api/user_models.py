"""
user_models.py -- Pydantic models for User and Profile (AUTH-01).

Same pattern as models.py's Supplier models: an Enum restricts `role`
to a fixed set of values, and separate Create/Public/Update models
control exactly what a client can send in vs. what they get back --
in particular, hashed_password never appears in a response model.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


# ---------------------------------------------------------------------------
# User -- credentials only (id, email, hashed_password, is_active, role,
# created_at). No name/phone/address here -- those live on Profile.
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Body for POST /users. Plain-text `password` never gets stored --
    the route layer hashes it before it touches the database. Optional
    profile fields let registration create the linked Profile in the
    same call, per the brief."""
    email: str
    password: str = Field(..., min_length=8)
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class User(BaseModel):
    """The full record as stored in TinyDB. Internal use only -- never
    returned directly from a route."""
    id: int
    email: str
    hashed_password: str
    is_active: bool = True
    role: Role = Role.USER
    created_at: datetime


class UserPublic(BaseModel):
    """What routes actually return -- everything about User except the
    password hash."""
    id: int
    email: str
    is_active: bool
    role: Role
    created_at: datetime


class UserUpdate(BaseModel):
    """Body for PUT /users/{id}. Only credential fields, per the brief --
    email and role. Anything not sent is left unchanged."""
    email: Optional[str] = None
    role: Optional[Role] = None


# ---------------------------------------------------------------------------
# Profile -- display name + contact data, one-to-one with a User.
# ---------------------------------------------------------------------------

class Profile(BaseModel):
    id: int
    user_id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth -- what POST /auth/login returns, and what's inside a decoded token.
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    """What GET /auth/me returns: email, role, plus the linked Profile."""
    email: str
    role: Role
    profile: Profile