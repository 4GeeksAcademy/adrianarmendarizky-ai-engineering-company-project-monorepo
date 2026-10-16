"""Access control on supplier routes (OWASP A01, gap G1). Written before the fix."""
import user_service as svc

SUPPLIER = {
    "name": "Test Carnes",
    "country": "USA",
    "categories": ["carne"],
    "rate_per_unit": 5.0,
    "currency": "USD",
}


def _set_role(user_id, role):
    svc.users_table.update({"role": role}, doc_ids=[user_id])


def _new_supplier(client, headers):
    resp = client.post("/suppliers", json=SUPPLIER, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _manager(register_and_login):
    manager = register_and_login(email="manager@example.com")
    _set_role(manager["user_id"], "manager")
    return manager


def test_a_plain_user_cannot_suspend_a_supplier(client, register_and_login):
    user = register_and_login(email="user@example.com")
    sid = _new_supplier(client, user["headers"])
    resp = client.patch(f"/suppliers/{sid}/status", json={"status": "suspended"}, headers=user["headers"])
    assert resp.status_code == 403


def test_a_plain_user_cannot_delete_a_supplier(client, register_and_login):
    user = register_and_login(email="user@example.com")
    sid = _new_supplier(client, user["headers"])
    resp = client.delete(f"/suppliers/{sid}", headers=user["headers"])
    assert resp.status_code == 403


def test_a_plain_user_cannot_change_a_suppliers_rate(client, register_and_login):
    user = register_and_login(email="user@example.com")
    sid = _new_supplier(client, user["headers"])
    resp = client.patch(f"/suppliers/{sid}/rate", json={"rate_per_unit": 6.5}, headers=user["headers"])
    assert resp.status_code == 403


def test_a_manager_can_suspend_a_supplier(client, register_and_login):
    manager = _manager(register_and_login)
    sid = _new_supplier(client, manager["headers"])
    resp = client.patch(f"/suppliers/{sid}/status", json={"status": "suspended"}, headers=manager["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"


def test_a_manager_can_delete_a_supplier(client, register_and_login):
    manager = _manager(register_and_login)
    sid = _new_supplier(client, manager["headers"])
    resp = client.delete(f"/suppliers/{sid}", headers=manager["headers"])
    assert resp.status_code == 200


def test_a_manager_can_change_a_suppliers_rate(client, register_and_login):
    manager = _manager(register_and_login)
    sid = _new_supplier(client, manager["headers"])
    resp = client.patch(f"/suppliers/{sid}/rate", json={"rate_per_unit": 6.5}, headers=manager["headers"])
    assert resp.status_code == 200
    assert resp.json()["rate_per_unit"] == 6.5


def test_a_plain_user_can_still_read_suppliers(client, register_and_login):
    user = register_and_login(email="user@example.com")
    sid = _new_supplier(client, user["headers"])
    resp = client.get("/suppliers", headers=user["headers"])
    assert resp.status_code == 200
    assert sid in [s["id"] for s in resp.json()]


def test_a_request_with_no_login_is_still_rejected(client):
    resp = client.patch("/suppliers/1/status", json={"status": "suspended"})
    assert resp.status_code == 401
