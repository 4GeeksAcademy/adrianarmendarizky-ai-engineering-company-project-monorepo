"""
tests/conftest.py -- shared fixtures for the AUTH-088 test suite.

Import order matters a lot in this file. Two things have to happen
BEFORE anything in the app (main, routes, database, security, ...)
gets imported for the first time:

  1. JWT_SECRET_KEY must already be set in the environment --
     security.py reads it at import time and raises if it's missing.
  2. tinydb.TinyDB itself must already be patched to always use an
     in-memory store -- database.py builds one global `db = TinyDB(...)`
     at import time, and user_service.py / password_service.py import
     its tables directly (`from database import users_table`), so
     patching database.users_table *after* those modules have already
     imported it would be too late to have any effect.

Both of those happen at the top of this file, before the `from main
import app` line below. See TESTING.md for the reasoning.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-real-use")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("PASSWORD_RESET_EXPIRE_MINUTES", "30")
os.environ.setdefault("RESEND_API_KEY", "")

import tinydb  # noqa: E402
from tinydb.storages import MemoryStorage  # noqa: E402

_original_tinydb_init = tinydb.TinyDB.__init__


def _memory_only_init(self, *args, **kwargs):
    # Ignore whatever path/args the app passes in (database.py passes a
    # real file path) and always use an in-memory store instead.
    _original_tinydb_init(self, storage=MemoryStorage)


tinydb.TinyDB.__init__ = _memory_only_init

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import email_service  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db():
    """Runs before every test. Because the TinyDB patch above makes the
    whole app share one in-memory store for the life of the test
    process, tests would otherwise see each other's data -- this clears
    every table between tests."""
    database.db.drop_tables()
    yield
    database.db.drop_tables()


@pytest.fixture(autouse=True)
def no_real_emails(monkeypatch):
    """The test environment has no network access to Resend, and these
    tests care about the reset-token lifecycle, not whether a real
    email provider is reachable. Patched at the source module so every
    caller (routes/auth.py imports the function by name) picks it up."""
    calls = []

    def _fake_send(to_email, reset_url):
        calls.append((to_email, reset_url))

    monkeypatch.setattr(email_service, "send_password_reset_email", _fake_send)
    # routes/auth.py did `from email_service import send_password_reset_email`,
    # which bound its own reference -- patch that name too so both the
    # module-level lookup and the already-imported name are covered.
    import routes.auth as auth_routes

    monkeypatch.setattr(auth_routes, "send_password_reset_email", _fake_send)
    return calls


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def register_and_login(client):
    """Registers a new user and logs them in. Returns a dict with the
    user's email/password, the created user's id, and a ready-to-use
    Authorization header -- most protected-route tests just need this."""

    def _make(email="user@example.com", password="password123", **profile_fields):
        register_resp = client.post(
            "/users",
            json={"email": email, "password": password, **profile_fields},
        )
        assert register_resp.status_code == 201, register_resp.text
        user_id = register_resp.json()["id"]

        login_resp = client.post(
            "/auth/login", data={"username": email, "password": password}
        )
        assert login_resp.status_code == 200, login_resp.text
        token = login_resp.json()["access_token"]

        return {
            "email": email,
            "password": password,
            "user_id": user_id,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _make
