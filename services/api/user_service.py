"""
user_service.py -- business logic for User and Profile (AUTH-01).

This is the "service layer" the brief asks for: routes call these
functions and stay thin (parse the request, call a function, shape
the response). All the actual rules -- hash the password, don't allow
two users with the same email, delete a user's profile along with the
user -- live here, in one place, instead of being duplicated across
routes.

Raises plain Python exceptions (defined below) instead of raising
HTTPException directly -- that keeps this module independent of
FastAPI, and lets the route layer decide the HTTP status code.
"""

from datetime import datetime, timezone

from tinydb import Query as TinyDBQuery

from database import profiles_table, users_table
from security import hash_password
from user_models import Profile, Role, User, UserCreate, UserUpdate

UserField = TinyDBQuery()
ProfileField = TinyDBQuery()


class UserNotFoundError(Exception):
    pass


class EmailAlreadyRegisteredError(Exception):
    pass


def _doc_to_user(doc) -> User:
    data = dict(doc)
    data["id"] = doc.doc_id
    return User(**data)


def _doc_to_profile(doc) -> Profile:
    data = dict(doc)
    data["id"] = doc.doc_id
    return Profile(**data)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def get_user_by_id(user_id: int) -> User | None:
    doc = users_table.get(doc_id=user_id)
    return _doc_to_user(doc) if doc else None


def get_user_by_email(email: str) -> User | None:
    doc = users_table.get(UserField.email == email)
    return _doc_to_user(doc) if doc else None


def create_user(user_in: UserCreate) -> User:
    """Hashes the password, inserts the User row, and always creates a
    linked Profile row (even if name/phone/address were left blank) --
    so GET /profiles/me never has to handle "profile doesn't exist yet"
    for a user that's already registered."""
    if get_user_by_email(user_in.email) is not None:
        raise EmailAlreadyRegisteredError(f"{user_in.email} is already registered")

    user_record = {
        "email": user_in.email,
        "hashed_password": hash_password(user_in.password),
        "is_active": True,
        "role": Role.USER.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    user_doc_id = users_table.insert(user_record)
    new_user = _doc_to_user(users_table.get(doc_id=user_doc_id))

    profiles_table.insert(
        {
            "user_id": new_user.id,
            "name": user_in.name,
            "phone": user_in.phone,
            "address": user_in.address,
        }
    )
    return new_user


def update_user(user_id: int, updates: UserUpdate) -> User:
    if get_user_by_id(user_id) is None:
        raise UserNotFoundError(f"User {user_id} not found")

    # exclude_unset=True -- only fields the caller actually sent get
    # changed; anything left out of the request body is untouched.
    changes = updates.model_dump(exclude_unset=True)

    if "email" in changes:
        existing = get_user_by_email(changes["email"])
        if existing is not None and existing.id != user_id:
            raise EmailAlreadyRegisteredError(f"{changes['email']} is already registered")

    if changes:
        users_table.update(changes, doc_ids=[user_id])

    return _doc_to_user(users_table.get(doc_id=user_id))


def delete_user(user_id: int) -> None:
    """Removes the User row and its linked Profile row together, so a
    deleted user never leaves an orphaned profile behind."""
    if get_user_by_id(user_id) is None:
        raise UserNotFoundError(f"User {user_id} not found")

    profile_doc = profiles_table.get(ProfileField.user_id == user_id)
    if profile_doc is not None:
        profiles_table.remove(doc_ids=[profile_doc.doc_id])

    users_table.remove(doc_ids=[user_id])


def list_users() -> list[User]:
    return [_doc_to_user(doc) for doc in users_table.all()]


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def get_profile_by_user_id(user_id: int) -> Profile | None:
    doc = profiles_table.get(ProfileField.user_id == user_id)
    return _doc_to_profile(doc) if doc else None


def update_profile(user_id: int, changes: dict) -> Profile:
    profile = get_profile_by_user_id(user_id)
    if profile is None:
        raise UserNotFoundError(f"No profile found for user {user_id}")

    if changes:
        profiles_table.update(changes, doc_ids=[profile.id])

    return get_profile_by_user_id(user_id)