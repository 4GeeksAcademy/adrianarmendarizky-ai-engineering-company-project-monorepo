"""Size limits on POST /telemetry/events (OWASP A04/A09). Written before the
fix. The database is replaced by a fake, so nothing real is stored."""
import json

import pytest

from database import get_db
from main import app


class _FakeDB:
    def add_all(self, records):
        self.added = list(records)

    def commit(self):
        pass


@pytest.fixture(autouse=True)
def fake_db():
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    yield
    app.dependency_overrides.pop(get_db, None)


def _event(i, properties=None):
    return {
        "eventId": f"e{i}",
        "timestamp": "2026-10-15T12:00:00Z",
        "sessionId": "s1",
        "event_type": "page_view",
        "schemaVersion": 1,
        "properties": properties or {},
    }


def test_a_normal_batch_of_20_events_is_accepted(client):
    resp = client.post("/telemetry/events", json={"events": [_event(i) for i in range(20)]})
    assert resp.status_code == 200
    assert resp.json() == {"received": 20, "stored": 20, "rejected": 0}


def test_too_many_events_in_one_request_is_refused(client):
    resp = client.post("/telemetry/events", json={"events": [_event(i) for i in range(101)]})
    assert resp.status_code == 413


def test_a_huge_request_body_is_refused(client):
    big = {"events": [_event(1, {"blob": "x" * 300_000})]}
    resp = client.post("/telemetry/events", json=big)
    assert resp.status_code == 413


def test_a_text_plain_beacon_body_still_works(client):
    body = json.dumps({"events": [_event(i) for i in range(3)]})
    resp = client.post("/telemetry/events", content=body, headers={"Content-Type": "text/plain"})
    assert resp.status_code == 200
    assert resp.json()["received"] == 3


def test_a_malformed_body_still_returns_zero_counts(client):
    resp = client.post("/telemetry/events", content="not json", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 200
    assert resp.json()["received"] == 0
