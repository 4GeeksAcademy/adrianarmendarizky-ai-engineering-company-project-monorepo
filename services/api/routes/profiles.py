"""
routes/profiles.py -- /profiles endpoints (AUTH-01).

Both routes act on "me" -- the caller identified by their token --
rather than taking a profile id in the URL. That's what "only the
profile owner may update it" means here: there's no {id} to swap in
for someone else's profile in the first place.
"""

from fastapi import APIRouter, Depends, HTTPException

import user_service as svc
from dependencies import get_current_user
from user_models import Profile, ProfileUpdate, User

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/me", response_model=Profile)
def read_my_profile(current_user: User = Depends(get_current_user)):
    profile = svc.get_profile_by_user_id(current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/me", response_model=Profile)
def update_my_profile(
    updates: ProfileUpdate, current_user: User = Depends(get_current_user)
):
    changes = updates.model_dump(exclude_unset=True)
    try:
        return svc.update_profile(current_user.id, changes)
    except svc.UserNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")