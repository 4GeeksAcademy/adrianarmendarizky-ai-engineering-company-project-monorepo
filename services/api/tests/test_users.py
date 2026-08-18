"""/users -- list, get, update, delete. All require auth except
POST (covered in test_register.py). See TESTING.md for the plan."""

import database


def _promote_to_admin(user_id):
    """Test setup helper -- there's no API route to grant admin, so we
    reach into the (in-memory, isolated) table directly. Not itself
    something under test."""
    database.users_table.update({"role": "admin"}, doc_ids=[user_id])


def test_list_users_happy_path(client, register_and_login):
    session = register_and_login()

    resp = client.get("/users", headers=session["headers"])

    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert session["email"] in emails


def test_list_users_requires_auth(client):
    resp = client.get("/users")
    assert resp.status_code == 401


def test_get_user_happy_path(client, register_and_login):
    session = register_and_login()

    resp = client.get(f"/users/{session['user_id']}", headers=session["headers"])

    assert resp.status_code == 200
    assert resp.json()["email"] == session["email"]


def test_get_user_not_found(client, register_and_login):
    session = register_and_login()

    resp = client.get("/users/999999", headers=session["headers"])

    assert resp.status_code == 404


def test_update_own_email_happy_path(client, register_and_login):
    session = register_and_login()

    resp = client.put(
        f"/users/{session['user_id']}",
        json={"email": "updated@example.com"},
        headers=session["headers"],
    )

    assert resp.status_code == 200
    assert resp.json()["email"] == "updated@example.com"


def test_admin_can_update_another_user(client, register_and_login):
    """Edge case: an admin, not just the user themselves, may update
    someone else's record."""
    admin = register_and_login(email="admin@example.com")
    _promote_to_admin(admin["user_id"])
    other = register_and_login(email="someoneelse@example.com")

    resp = client.put(
        f"/users/{other['user_id']}",
        json={"email": "changed-by-admin@example.com"},
        headers=admin["headers"],
    )

    assert resp.status_code == 200
    assert resp.json()["email"] == "changed-by-admin@example.com"


def test_update_someone_elses_email_forbidden(client, register_and_login):
    """Failure mode: a non-owner, non-admin gets 403 -- checked before
    the service layer even runs, per the code comment in routes/users.py."""
    user_a = register_and_login(email="usera@example.com")
    user_b = register_and_login(email="userb@example.com")

    resp = client.put(
        f"/users/{user_b['user_id']}",
        json={"email": "hijacked@example.com"},
        headers=user_a["headers"],
    )

    assert resp.status_code == 403


def test_update_own_email_to_one_already_taken(client, register_and_login):
    """Failure mode: updating your OWN email to one already registered
    to someone else is a 409, not a 403 -- the ownership check passes
    (it's your own record), it's the duplicate-email check that fails."""
    register_and_login(email="taken@example.com")
    session = register_and_login(email="wants-taken@example.com")

    resp = client.put(
        f"/users/{session['user_id']}",
        json={"email": "taken@example.com"},
        headers=session["headers"],
    )

    assert resp.status_code == 409


def test_update_user_not_found(client, register_and_login):
    session = register_and_login()

    resp = client.put(
        "/users/999999", json={"email": "x@example.com"}, headers=session["headers"]
    )

    assert resp.status_code == 404


def test_delete_user_happy_path(client, register_and_login):
    to_delete = register_and_login(email="deleteme@example.com")
    # A second, still-valid session to check the result with -- to_delete's
    # own token stops working the instant its user is gone (see
    # test_token.py::test_token_for_deleted_user), so it can't be used to
    # verify the deletion itself.
    other = register_and_login(email="witness@example.com")

    resp = client.delete(f"/users/{to_delete['user_id']}", headers=other["headers"])

    assert resp.status_code == 200
    follow_up = client.get(f"/users/{to_delete['user_id']}", headers=other["headers"])
    assert follow_up.status_code == 404


def test_delete_user_not_found(client, register_and_login):
    session = register_and_login()

    resp = client.delete("/users/999999", headers=session["headers"])

    assert resp.status_code == 404


def test_delete_user_requires_auth(client, register_and_login):
    session = register_and_login()

    resp = client.delete(f"/users/{session['user_id']}")

    assert resp.status_code == 401
