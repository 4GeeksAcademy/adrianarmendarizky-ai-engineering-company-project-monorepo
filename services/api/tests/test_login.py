"""POST /auth/login. See TESTING.md for the plan."""


def test_login_happy_path(client):
    client.post(
        "/users", json={"email": "login@example.com", "password": "password123"}
    )

    resp = client.post(
        "/auth/login", data={"username": "login@example.com", "password": "password123"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    # The token actually works on a protected route.
    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "login@example.com"


def test_login_wrong_password_and_unknown_email_give_identical_response(client):
    """Edge case: the brief requires these two failure cases to be
    indistinguishable, so an attacker can't use the error to learn which
    emails are registered."""
    client.post(
        "/users", json={"email": "registered@example.com", "password": "password123"}
    )

    wrong_password = client.post(
        "/auth/login",
        data={"username": "registered@example.com", "password": "wrongpass"},
    )
    unknown_email = client.post(
        "/auth/login",
        data={"username": "nosuchuser@example.com", "password": "whatever1"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_login_wrong_password_failure(client):
    client.post(
        "/users", json={"email": "failcase@example.com", "password": "password123"}
    )

    resp = client.post(
        "/auth/login",
        data={"username": "failcase@example.com", "password": "not-the-password"},
    )

    assert resp.status_code == 401
