"""
tests/pipelines/test_rfp_events.py -- tests for the live RFP ticket
notifications (services/api/routes/rfp_events.py, services/api/sse_broker.py).

An SSE stream never ends, so a normal TestClient call would hang. These tests
read the stream's code directly instead (one event at a time) and use
TestClient only where the answer comes back right away (login checks, upload).
Nothing real is touched: the database is a throwaway in-memory SQLite.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

# security.py reads these the moment it is imported (see main.py's comment).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

import database  # noqa: E402
import routes.rfp as rfp_routes  # noqa: E402
import routes.rfp_events as events_routes  # noqa: E402
from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from rfp_models import RfpTicket  # noqa: E402
from sse_broker import broker  # noqa: E402


class FakeRequest:
    """Stands in for the browser's request: the client never disconnects."""

    async def is_disconnected(self):
        return False


@pytest.fixture()
def engine(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    return engine


def add_ticket(engine, filename="rfp.pdf"):
    with Session(engine) as db:
        ticket = RfpTicket(original_filename=filename, raw_pdf_path="data/raw/x.pdf")
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket.id


# --- login ----------------------------------------------------------------

def test_stream_rejects_a_missing_or_bad_token():
    app = FastAPI()
    app.include_router(events_routes.router)
    client = TestClient(app)

    assert client.get("/rfp/events").status_code == 401
    bad = client.get("/rfp/events", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad.status_code == 401


# --- what goes over the wire ------------------------------------------------

def test_stream_response_is_an_event_stream():
    async def run():
        response = await events_routes.rfp_events(
            request=FakeRequest(), last_event_id=None, _user=object()
        )
        await response.body_iterator.aclose()
        return response

    response = asyncio.run(run())
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"


def test_event_has_id_a_name_and_json_data():
    payload = {"ticket_id": 7, "status": "analyzing", "original_filename": "sunset.pdf"}

    async def run():
        stream = events_routes._event_stream(FakeRequest(), None)
        await stream.__anext__()  # ": connected" -- we are now subscribed
        broker.publish(payload)
        message = await stream.__anext__()
        await stream.aclose()
        return message

    message = asyncio.run(run())
    assert message.endswith("\n\n")
    lines = message.strip().split("\n")
    assert lines[0] == "id: 7"
    assert lines[1] == "event: rfp_ticket_created"
    assert lines[2].startswith("data: ")
    data = json.loads(lines[2][len("data: "):])
    assert data == payload


# --- reconnecting -----------------------------------------------------------

def test_reconnect_replays_missed_tickets_and_never_repeats_one(engine):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        add_ticket(engine, name)  # ids 1, 2, 3

    async def run():
        # The client saw ticket 1, then lost its connection.
        stream = events_routes._event_stream(FakeRequest(), 1)
        await stream.__anext__()  # ": connected"
        replay_2 = await stream.__anext__()
        replay_3 = await stream.__anext__()
        # Ticket 3 arrives live too (same one) -- it must be skipped.
        broker.publish({"ticket_id": 3, "status": "analyzing", "original_filename": "c.pdf"})
        broker.publish({"ticket_id": 4, "status": "analyzing", "original_filename": "d.pdf"})
        live_4 = await stream.__anext__()
        await stream.aclose()
        return replay_2, replay_3, live_4

    replay_2, replay_3, live_4 = asyncio.run(run())
    assert replay_2.startswith("id: 2\n")
    assert replay_3.startswith("id: 3\n")
    assert live_4.startswith("id: 4\n")  # not a second "id: 3"


def test_closing_the_connection_removes_its_queue():
    before = len(broker._queues)

    async def run():
        stream = events_routes._event_stream(FakeRequest(), None)
        await stream.__anext__()
        assert len(broker._queues) == before + 1
        await stream.aclose()

    asyncio.run(run())
    assert len(broker._queues) == before


# --- the event is sent when a ticket is registered ----------------------------

def test_uploading_a_pdf_publishes_rfp_ticket_created(engine, monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(rfp_routes.router)

    def _db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: object()
    monkeypatch.setattr(rfp_routes, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(rfp_routes, "process_ticket", lambda ticket_id: None)
    client = TestClient(app)

    queue = broker.subscribe()
    try:
        response = client.post(
            "/rfp/tickets",
            files={"file": ("sunset.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert response.status_code == 202
        message = queue.get_nowait()
    finally:
        broker.unsubscribe(queue)

    assert message["ticket_id"] == response.json()["ticket_id"]
    assert message["status"] == "analyzing"
    assert message["original_filename"] == "sunset.pdf"
