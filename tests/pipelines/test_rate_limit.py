"""Rate limit on the endpoints that call the model (NIST: Protect)."""
import os
import sys
import types
from datetime import datetime
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import rate_limit  # noqa: E402
import routes.agent as agent_routes  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from user_models import Role, User  # noqa: E402


def _client(user_id, monkeypatch, calls):
    """A test app where the agent is fake and logged in as `user_id`."""
    app = FastAPI()
    app.include_router(agent_routes.router)
    user = User(id=user_id, email=f"u{user_id}@brasaland.test", hashed_password="x",
                role=Role.MANAGER, created_at=datetime(2026, 1, 1))
    app.dependency_overrides[get_current_user] = lambda: user

    class FakeGraph:
        def invoke(self, graph_input, config):
            calls.append(graph_input)
            return {"answer": "hello", "memory_proposal": None}

    monkeypatch.setattr(agent_routes, "graph", FakeGraph())
    return TestClient(app)


def test_request_over_the_limit_gets_429_and_never_reaches_the_agent(monkeypatch):
    monkeypatch.setattr(rate_limit, "MAX_REQUESTS", 3)
    calls = []
    client = _client(7, monkeypatch, calls)
    for _ in range(3):
        assert client.post("/agent/query", json={"question": "hi"}).status_code == 200
    blocked = client.post("/agent/query", json={"question": "hi"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert len(calls) == 3  # the 4th request never ran the agent


def test_one_user_hitting_the_limit_does_not_block_another(monkeypatch):
    monkeypatch.setattr(rate_limit, "MAX_REQUESTS", 1)
    calls = []
    first = _client(7, monkeypatch, calls)
    second = _client(8, monkeypatch, calls)
    assert first.post("/agent/query", json={"question": "hi"}).status_code == 200
    assert first.post("/agent/query", json={"question": "hi"}).status_code == 429
    assert second.post("/agent/query", json={"question": "hi"}).status_code == 200


def test_the_limit_lifts_after_the_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rate_limit, "time", types.SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(rate_limit, "MAX_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "WINDOW_SECONDS", 60)
    assert rate_limit.check_rate_limit("1") is None
    assert rate_limit.check_rate_limit("1") is None
    assert rate_limit.check_rate_limit("1") is not None
    now[0] += 61
    assert rate_limit.check_rate_limit("1") is None
