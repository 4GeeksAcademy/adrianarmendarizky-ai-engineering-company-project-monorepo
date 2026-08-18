"""POST /auth/change-password. See TESTING.md for the plan."""


def test_change_password_happy_path(client, register_and_login):
    session = register_and_login(password="oldpassword1")

    resp = client.post(
        "/auth/change-password",
        json={"current_password": "oldpassword1", "new_password": "newpassword1"},
        headers=session["headers"],
    )
    assert resp.status_code == 200

    new_login = client.post(
        "/auth/login",
        data={"username": session["email"], "password": "newpassword1"},
    )
    assert new_login.status_code == 200


def test_change_password_new_password_too_short(client, register_and_login):
    session = register_and_login(password="oldpassword1")

    resp = client.post(
        "/auth/change-password",
        json={"current_password": "oldpassword1", "new_password": "short"},
        headers=session["headers"],
    )

    assert resp.status_code == 422


def test_change_password_wrong_current_password(client, register_and_login):
    session = register_and_login(password="oldpassword1")

    resp = client.post(
        "/auth/change-password",
        json={"current_password": "not-the-current-one", "new_password": "newpassword1"},
        headers=session["headers"],
    )

    assert resp.status_code == 400


def test_change_password_requires_auth(client):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "whatever1", "new_password": "newpassword1"},
    )
    assert resp.status_code == 401
