"""POST /users -- registration. See TESTING.md for the plan."""


def test_register_happy_path(client):
    resp = client.post(
        "/users",
        json={
            "email": "newuser@example.com",
            "password": "password123",
            "name": "New User",
            "phone": "555-0100",
            "address": "123 Main St",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    # UserPublic shape only -- the hash must never come back in a response.
    assert "hashed_password" not in body
    assert body["email"] == "newuser@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True

    # The linked profile was actually created with the submitted fields.
    login = client.post(
        "/auth/login", data={"username": "newuser@example.com", "password": "password123"}
    )
    token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["profile"]["name"] == "New User"
    assert me.json()["profile"]["phone"] == "555-0100"


def test_register_without_optional_profile_fields(client):
    """Edge case: no name/phone/address sent -- profile is still created,
    just with every field None (not skipped/missing)."""
    resp = client.post(
        "/users", json={"email": "bare@example.com", "password": "password123"}
    )
    assert resp.status_code == 201

    login = client.post(
        "/auth/login", data={"username": "bare@example.com", "password": "password123"}
    )
    token = login.json()["access_token"]
    profile = client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json() == {
        "id": profile.json()["id"],
        "user_id": profile.json()["user_id"],
        "name": None,
        "phone": None,
        "address": None,
    }


def test_register_password_too_short(client):
    resp = client.post(
        "/users", json={"email": "short@example.com", "password": "abc123"}
    )
    assert resp.status_code == 422


def test_register_missing_required_field(client):
    resp = client.post("/users", json={"email": "nopassword@example.com"})
    assert resp.status_code == 422


def test_register_duplicate_email(client):
    payload = {"email": "dupe@example.com", "password": "password123"}
    first = client.post("/users", json=payload)
    assert first.status_code == 201

    second = client.post("/users", json=payload)
    assert second.status_code == 409
