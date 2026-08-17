"""
routes/users.py -- /users endpoints (AUTH-01).

Every route below except POST /users now requires a valid token, via
get_current_user. PUT /users/{id} goes one step further: it checks
*whose* token it is -- only the user themselves or an admin may change
that user's credentials, per the brief. Everyone else gets a 403,
which is different from a 401: 401 means "I don't know who you are",
403 means "I know who you are, and you're not allowed to do this."
"""

from fastapi import APIRouter, Depends, HTTPException

import user_service as svc
from dependencies import get_current_user
from user_models import Role, User, UserCreate, UserPublic, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _get_user_or_404(user_id: int):
    user = svc.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


# ---------------------------------------------------------------------------
# POST /users -- register. Public: this is how an account gets created
# in the first place.
# ---------------------------------------------------------------------------

@router.post("", response_model=UserPublic, status_code=201)
def register_user(user_in: UserCreate):
    try:
        return svc.create_user(user_in)
    except svc.EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="Email already registered.")


# ---------------------------------------------------------------------------
# GET /users -- list all users. Protected.
# ---------------------------------------------------------------------------

@router.get("", response_model=list[UserPublic])
def list_users(current_user: User = Depends(get_current_user)):
    return svc.list_users()


# ---------------------------------------------------------------------------
# GET /users/{id}. Protected.
# ---------------------------------------------------------------------------

@router.get("/{user_id}", response_model=UserPublic)
def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    return _get_user_or_404(user_id)


# ---------------------------------------------------------------------------
# PUT /users/{id} -- update credential fields (email, role). Protected,
# and restricted to the user themselves or an admin.
# ---------------------------------------------------------------------------

@router.put("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int, updates: UserUpdate, current_user: User = Depends(get_current_user)
):
    _get_user_or_404(user_id)

    if current_user.id != user_id and current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=403, detail="Only the user themselves or an admin can do this"
        )

    try:
        return svc.update_user(user_id, updates)
    except svc.EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail="Email already registered.")


# ---------------------------------------------------------------------------
# DELETE /users/{id} -- also removes the linked profile. Protected.
# ---------------------------------------------------------------------------

@router.delete("/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_current_user)):
    _get_user_or_404(user_id)
    svc.delete_user(user_id)
    return {"detail": f"User {user_id} deleted"}