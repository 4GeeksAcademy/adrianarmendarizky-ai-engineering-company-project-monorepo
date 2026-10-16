"""Limit on failed logins (OWASP A07). Written before the fix."""
import pytest

import rate_limit


@pytest.fixture(autouse=True)
def clean_limits():
    rate_limit.reset()
    yield
    rate_limit.reset()


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_five_wrong_passwords_lock_the_account_for_a_while(client, register_and_login):
    register_and_login(email="victim@example.com", password="password123")
    for _ in range(5):
        assert _login(client, "victim@example.com", "wrong-password").status_code == 401
    resp = _login(client, "victim@example.com", "password123")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_a_few_wrong_tries_then_the_right_password_still_works(client, register_and_login):
    register_and_login(email="user@example.com", password="password123")
    for _ in range(3):
        assert _login(client, "user@example.com", "wrong-password").status_code == 401
    assert _login(client, "user@example.com", "password123").status_code == 200


def test_one_emails_lockout_does_not_block_another(client, register_and_login):
    register_and_login(email="victim@example.com", password="password123")
    register_and_login(email="other@example.com", password="password123")
    for _ in range(6):
        _login(client, "victim@example.com", "wrong-password")
    assert _login(client, "other@example.com", "password123").status_code == 200


def test_an_unknown_email_is_limited_too(client):
    for _ in range(5):
        assert _login(client, "nobody@example.com", "whatever123").status_code == 401
    assert _login(client, "nobody@example.com", "whatever123").status_code == 429
