"""Access control on user accounts (OWASP A01). Written before the fix."""
import user_service as svc


def _make_admin(user_id):
    svc.users_table.update({"role": "admin"}, doc_ids=[user_id])


def test_registration_ignores_a_role_sent_by_the_caller(client):
    resp = client.post("/users", json={"email": "new@example.com", "password": "password123", "role": "admin"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


def test_a_user_cannot_make_themselves_admin(client, register_and_login):
    me = register_and_login(email="me@example.com")
    resp = client.put(f"/users/{me['user_id']}", json={"role": "admin"}, headers=me["headers"])
    assert resp.status_code == 403


def test_a_user_can_still_change_their_own_email(client, register_and_login):
    me = register_and_login(email="me@example.com")
    resp = client.put(f"/users/{me['user_id']}", json={"email": "me2@example.com"}, headers=me["headers"])
    assert resp.status_code == 200


def test_an_admin_can_change_a_role(client, register_and_login):
    admin = register_and_login(email="admin@example.com")
    other = register_and_login(email="other@example.com")
    _make_admin(admin["user_id"])
    resp = client.put(f"/users/{other['user_id']}", json={"role": "manager"}, headers=admin["headers"])
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


def test_a_user_cannot_delete_someone_elses_account(client, register_and_login):
    me = register_and_login(email="me@example.com")
    other = register_and_login(email="other@example.com")
    resp = client.delete(f"/users/{other['user_id']}", headers=me["headers"])
    assert resp.status_code == 403


def test_a_user_can_delete_their_own_account(client, register_and_login):
    me = register_and_login(email="me@example.com")
    resp = client.delete(f"/users/{me['user_id']}", headers=me["headers"])
    assert resp.status_code == 200


def test_an_admin_can_delete_another_account(client, register_and_login):
    admin = register_and_login(email="admin@example.com")
    other = register_and_login(email="other@example.com")
    _make_admin(admin["user_id"])
    resp = client.delete(f"/users/{other['user_id']}", headers=admin["headers"])
    assert resp.status_code == 200
