"""Token validation, exercised through GET /auth/me (the simplest route
protected by get_current_user). See TESTING.md for the plan."""

from datetime import datetime, timedelta, timezone

from jose import jwt

import security


def _build_token(user_id, minutes_from_now):
    """Builds a JWT the same way security.create_access_token does, but
    with a caller-controlled expiry -- used to construct an already-
    expired token, which the real helper has no way to produce."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, security.SECRET_KEY, algorithm=security.ALGORITHM)


def test_valid_token_happy_path(client, register_and_login):
    session = register_and_login()

    resp = client.get("/auth/me", headers=session["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == session["email"]
    assert body["role"] == "user"


def test_token_for_deleted_user(client, register_and_login):
    """Edge case: token is validly signed and unexpired, but the user it
    points to has since been deleted -- must be 401, not a 500."""
    session = register_and_login()
    delete_resp = client.delete(f"/users/{session['user_id']}", headers=session["headers"])
    assert delete_resp.status_code == 200

    resp = client.get("/auth/me", headers=session["headers"])

    assert resp.status_code == 401


def test_missing_authorization_header(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_malformed_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_expired_token(client, register_and_login):
    session = register_and_login()
    expired_token = _build_token(session["user_id"], minutes_from_now=-5)

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert resp.status_code == 401
