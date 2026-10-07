"""
tests/pipelines/test_rfp_events.py -- tests for the live RFP ticket
notifications (services/api/routes/rfp_events.py, services/api/rfp_notify.py,
services/api/sse_broker.py).

An SSE stream never ends, so a normal TestClient call would hang. These tests
read the stream's code directly (one event at a time) and use TestClient only
where the answer comes back right away (login checks, upload).
Nothing real is touched: the database is a throwaway in-memory SQLite.
"""

import asyncio
import json
import os
import sys
import threading
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
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import database  # noqa: E402
import routes.rfp as rfp_routes  # noqa: E402
import routes.rfp_events as events_routes  # noqa: E402
from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from rfp_models import RfpEvent, RfpTicket  # noqa: E402
from rfp_notify import store_and_notify  # noqa: E402
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


def trace_event(ticket_id, agent, event_type="node_finished", client="Sunset Bay Resorts, LLC"):
    """A trace event as the pipeline sends it (see data/pipelines/rfp_trace.py)."""
    output = {}
    if agent == "intake:orchestrate" and event_type == "node_finished":
        output = {"metadata": {
            "rfp_id": "SBR-1", "client_name": client, "location": "Florida",
            "service_type": "co-branded concession",
        }}
    return {
        "ticket_id": ticket_id, "part": 1, "agent": agent, "event_type": event_type,
        "subject": None, "input": {}, "output": output, "actor": None, "timestamp": None,
    }


def add_orchestrate_row(engine, ticket_id, client="Acme Catering"):
    """Save an orchestrate event straight into rfp_events; returns its row id."""
    with Session(engine) as db:
        row = RfpEvent(
            ticket_id=ticket_id, part=1, agent="intake:orchestrate", event_type="node_finished",
            output_data={"metadata": {
                "rfp_id": f"R-{ticket_id}", "client_name": client, "location": "Medellin",
                "service_type": "recurring_catering",
            }},
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


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
    data = {"ticket_id": 7, "rfp_id": "SBR-1", "status": "analyzing"}

    async def run():
        stream = events_routes._event_stream(FakeRequest(), None)
        await stream.__anext__()  # ": connected" -- we are now subscribed
        broker.publish({"id": 87, "data": data})
        message = await stream.__anext__()
        await stream.aclose()
        return message

    message = asyncio.run(run())
    assert message.endswith("\n\n")
    lines = message.strip().split("\n")
    assert lines[0] == "id: 87"  # the saved event's number, not the ticket's
    assert lines[1] == "event: rfp_ticket_created"
    assert lines[2].startswith("data: ")
    assert json.loads(lines[2][len("data: "):]) == data


# --- when and what we notify ---------------------------------------------------

def test_notification_has_the_part_1_context_fields(engine):
    ticket_id = add_ticket(engine)
    queue = broker.subscribe()
    try:
        store_and_notify(trace_event(ticket_id, "intake:orchestrate"))
        message = queue.get_nowait()
    finally:
        broker.unsubscribe(queue)

    assert set(message["data"]) == {
        "ticket_id", "rfp_id", "client_name", "location", "service_type", "status", "created_at",
    }
    assert message["data"]["ticket_id"] == ticket_id
    assert message["data"]["client_name"] == "Sunset Bay Resorts, LLC"
    assert message["data"]["status"] == "analyzing"
    assert message["data"]["created_at"].endswith("Z")
    with Session(engine) as db:
        saved = db.exec(select(RfpEvent).where(RfpEvent.agent == "intake:orchestrate")).one()
    assert message["id"] == saved.id  # the SSE id is the saved event's own number


def test_only_a_finished_orchestrate_step_notifies(engine):
    ticket_id = add_ticket(engine)
    queue = broker.subscribe()
    try:
        # A document the classifier rejected stops after "classify": it never notifies.
        store_and_notify(trace_event(ticket_id, "intake:convert"))
        store_and_notify(trace_event(ticket_id, "intake:classify"))
        # A failed orchestrate step is not "accepted and processing" either.
        store_and_notify(trace_event(ticket_id, "intake:orchestrate", event_type="node_failed"))
        assert queue.empty()
    finally:
        broker.unsubscribe(queue)

    with Session(engine) as db:
        saved = db.exec(select(RfpEvent)).all()
    assert len(saved) == 3  # every trace event is still saved, as before


def test_uploading_a_pdf_does_not_notify_by_itself(engine, monkeypatch, tmp_path):
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
        assert queue.empty()  # it only notifies once the document is accepted as an RFP
    finally:
        broker.unsubscribe(queue)


def test_a_message_published_from_another_thread_reaches_the_stream():
    # The pipeline runs in a background thread; the stream lives in the event loop.
    async def run():
        stream = events_routes._event_stream(FakeRequest(), None)
        await stream.__anext__()  # ": connected"
        sender = threading.Thread(
            target=broker.publish, args=({"id": 5, "data": {"ticket_id": 1}},)
        )
        sender.start()
        message = await asyncio.wait_for(stream.__anext__(), timeout=5)
        sender.join()
        await stream.aclose()
        return message

    assert asyncio.run(run()).startswith("id: 5\n")


# --- reconnecting -----------------------------------------------------------

def test_reconnect_replays_missed_notifications_and_never_repeats_one(engine):
    t1, t2, t3, t4 = (add_ticket(engine, name) for name in ("a.pdf", "b.pdf", "c.pdf", "notrfp.pdf"))
    e1 = add_orchestrate_row(engine, t1)
    e2 = add_orchestrate_row(engine, t2)
    # t4 was rejected by the classifier: it only has a "classify" event, so no notification.
    with Session(engine) as db:
        db.add(RfpEvent(ticket_id=t4, part=1, agent="intake:classify", event_type="node_finished"))
        db.commit()
    e3 = add_orchestrate_row(engine, t3)

    async def run():
        # The client saw the first notification, then lost its connection.
        stream = events_routes._event_stream(FakeRequest(), e1)
        await stream.__anext__()  # ": connected"
        replay_2 = await stream.__anext__()
        replay_3 = await stream.__anext__()
        # The last one also arrives live (a duplicate) and a brand new one follows.
        broker.publish({"id": e3, "data": {"ticket_id": t3}})
        broker.publish({"id": e3 + 1, "data": {"ticket_id": 99}})
        live = await stream.__anext__()
        await stream.aclose()
        return replay_2, replay_3, live

    replay_2, replay_3, live = asyncio.run(run())
    assert replay_2.startswith(f"id: {e2}\n")
    assert replay_3.startswith(f"id: {e3}\n")  # the rejected ticket t4 was skipped
    assert '"client_name": "Acme Catering"' in replay_3  # same payload as a live one
    assert live.startswith(f"id: {e3 + 1}\n")  # not a second copy of e3


def test_closing_the_connection_removes_its_queue():
    before = broker.subscriber_count()

    async def run():
        stream = events_routes._event_stream(FakeRequest(), None)
        await stream.__anext__()
        assert broker.subscriber_count() == before + 1
        await stream.aclose()

    asyncio.run(run())
    assert broker.subscriber_count() == before
