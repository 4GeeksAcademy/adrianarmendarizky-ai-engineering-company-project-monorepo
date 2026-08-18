"""GET/PUT /profiles/me. See TESTING.md for the plan."""


def test_get_my_profile_happy_path(client, register_and_login):
    session = register_and_login(name="Jane Doe", phone="555-0101")

    resp = client.get("/profiles/me", headers=session["headers"])

    assert resp.status_code == 200
    assert resp.json()["name"] == "Jane Doe"
    assert resp.json()["phone"] == "555-0101"


def test_update_my_profile_partial_update(client, register_and_login):
    session = register_and_login(name="Original Name", phone="555-0000")

    resp = client.put(
        "/profiles/me", json={"phone": "555-9999"}, headers=session["headers"]
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["phone"] == "555-9999"
    assert body["name"] == "Original Name"  # untouched


def test_update_my_profile_empty_body_leaves_it_unchanged(client, register_and_login):
    session = register_and_login(name="Stays The Same", phone="555-1111")

    resp = client.put("/profiles/me", json={}, headers=session["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Stays The Same"
    assert body["phone"] == "555-1111"


def test_get_my_profile_requires_auth(client):
    resp = client.get("/profiles/me")
    assert resp.status_code == 401


def test_update_my_profile_requires_auth(client):
    resp = client.put("/profiles/me", json={"phone": "555-0000"})
    assert resp.status_code == 401
