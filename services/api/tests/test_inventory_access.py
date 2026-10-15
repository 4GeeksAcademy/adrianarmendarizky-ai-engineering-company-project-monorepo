"""Login requirements on inventory read routes (OWASP A01, gap G9).
Written before the fix. The database is replaced by a fake, so these
tests never touch Supabase."""
import pytest
from fastapi.testclient import TestClient

from database import get_db
from main import app


class _FakeResult:
    def all(self):
        return []

    def first(self):
        return None


class _FakeDB:
    def exec(self, *args, **kwargs):
        return _FakeResult()

    def get(self, *args, **kwargs):
        return None


@pytest.fixture
def api():
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_db, None)


def test_listing_products_stays_open_without_login(api):
    # The MCP server reads this route without a token, so it stays open for now.
    assert api.get("/inventory/products").status_code != 401


def test_no_login_cannot_read_one_product(api):
    assert api.get("/inventory/products/1").status_code == 401


def test_no_login_cannot_list_orders(api):
    assert api.get("/inventory/orders").status_code == 401


def test_a_logged_in_user_can_still_read_one_product(api, register_and_login):
    user = register_and_login(email="user@example.com")
    resp = api.get("/inventory/products/1", headers=user["headers"])
    assert resp.status_code == 404  # the fake database has no products


def test_a_logged_in_user_can_still_list_orders(api, register_and_login):
    user = register_and_login(email="user@example.com")
    resp = api.get("/inventory/orders", headers=user["headers"])
    assert resp.status_code not in (401, 403)
