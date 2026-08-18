"""POST /auth/forgot-password, POST /auth/reset-password.
See TESTING.md for the plan."""

from datetime import datetime, timedelta, timezone

from tinydb import Query

import database


def _get_raw_reset_token(client, monkeypatch, email):
    """Test helper: forgot-password only ever returns the raw token via
    the (mocked) email, never in the HTTP response -- so tests intercept
    it the same way the real email would carry it."""
    captured = {}

    def _capture(to_email, reset_url):
        captured["url"] = reset_url

    import routes.auth as auth_routes

    monkeypatch.setattr(auth_routes, "send_password_reset_email", _capture)

    resp = client.post("/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    return captured["url"].split("token=")[1]


def test_forgot_password_happy_path_triggers_email(client, monkeypatch, register_and_login):
    session = register_and_login(email="forgot@example.com")

    token = _get_raw_reset_token(client, monkeypatch, session["email"])

    assert token  # a real token was generated and "emailed"


def test_forgot_password_unknown_email_same_response_no_email_sent(
    client, no_real_emails
):
    """Edge case: unknown email gets the identical 200 message, and no
    email is attempted -- confirms the anti-enumeration behavior."""
    resp = client.post("/auth/forgot-password", json={"email": "nosuchuser@example.com"})

    assert resp.status_code == 200
    assert resp.json()["detail"] == (
        "If that address is registered, you'll receive a reset link shortly."
    )
    assert no_real_emails == []  # the fake send was never called


def test_reset_password_happy_path(client, monkeypatch, register_and_login):
    session = register_and_login(email="reset@example.com", password="oldpassword1")
    token = _get_raw_reset_token(client, monkeypatch, session["email"])

    resp = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "newpassword1"}
    )
    assert resp.status_code == 200

    old_login = client.post(
        "/auth/login",
        data={"username": session["email"], "password": "oldpassword1"},
    )
    new_login = client.post(
        "/auth/login",
        data={"username": session["email"], "password": "newpassword1"},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_reset_password_garbage_token(client):
    resp = client.post(
        "/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "newpassword1"},
    )
    assert resp.status_code == 400


def test_reset_password_expired_token(client, monkeypatch, register_and_login):
    session = register_and_login(email="expired@example.com")
    token = _get_raw_reset_token(client, monkeypatch, session["email"])

    # Reach into the (isolated, in-memory) table to backdate the
    # already-issued token's expiry -- there's no way to do this through
    # the API itself, since expiry is fixed to "now + N minutes" at
    # creation.
    Reset = Query()
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    database.password_resets_table.update({"expires_at": past}, Reset.token_hash.exists())

    resp = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "newpassword1"}
    )
    assert resp.status_code == 400


def test_reset_password_token_already_used(client, monkeypatch, register_and_login):
    session = register_and_login(email="reused@example.com")
    token = _get_raw_reset_token(client, monkeypatch, session["email"])

    first = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "newpassword1"}
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "anotherpassword"}
    )
    assert second.status_code == 400
