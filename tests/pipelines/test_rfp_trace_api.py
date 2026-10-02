"""
tests/pipelines/test_rfp_trace_api.py -- the API side of the Part 1 and Part 2
trace (services/api/routes/rfp.py, services/api/rfp_trace_store.py): the
background runs switch the trace on around the pipeline, every draft round is
saved as an event, and a trace that cannot be saved never stops the work.

The pipelines are replaced by fakes, as in test_rfp_generation_api.py (whose
helpers are reused here). The database is a throwaway in-memory SQLite.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import database  # noqa: E402
import rfp_trace  # noqa: E402
import rfp_trace_store  # noqa: E402
import routes.rfp as rfp_routes  # noqa: E402
from rfp_models import DepartmentSection, RfpEvent, RfpMetadata, RfpTicket  # noqa: E402
from test_rfp_generation_api import (  # noqa: E402  (the helpers of the generation API tests)
    REAL_PROCESS_GENERATION, add_ticket, passed_result, ticket_of,
)

STATE = {"status": "under_evaluation", "average_iterations": 1.0, "results": {
    "marketing": passed_result("marketing", "## Marketing draft"),
    "operaciones": passed_result("operaciones", "## Operations draft"),
}}


def make_engine(monkeypatch, with_events=True):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [RfpTicket.__table__, RfpMetadata.__table__, DepartmentSection.__table__]
    if with_events:
        tables.append(RfpEvent.__table__)
    SQLModel.metadata.create_all(eng, tables=tables)
    monkeypatch.setattr(database, "engine", eng)
    return eng


@pytest.fixture()
def engine(monkeypatch):
    return make_engine(monkeypatch)


def events_of(engine, ticket_id):
    with Session(engine) as db:
        return db.exec(select(RfpEvent).where(RfpEvent.ticket_id == ticket_id).order_by(RfpEvent.id)).all()


# --- Part 2: generation ----------------------------------------------------------------------

def test_every_draft_round_of_every_department_is_saved_as_an_event_in_order(engine, monkeypatch):
    def fake(ticket_id, metadata, inputs, on_progress=None):
        for department in ("marketing", "operaciones"):
            on_progress(department, "drafting", 1)
            on_progress(department, "evaluating", 1)
        on_progress("operaciones", "drafting", 2)
        on_progress("operaciones", "evaluating", 2)
        for department in ("marketing", "operaciones"):
            on_progress(department, "finished", 1 if department == "marketing" else 2)
        return STATE

    monkeypatch.setattr(rfp_routes, "run_response", fake)
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    events = events_of(engine, ticket_id)
    assert [(e.agent, e.subject, e.input_data["draft"]) for e in events] == [
        ("response:drafting", "marketing", 1), ("response:evaluating", "marketing", 1),
        ("response:drafting", "operaciones", 1), ("response:evaluating", "operaciones", 1),
        ("response:drafting", "operaciones", 2), ("response:evaluating", "operaciones", 2),
        ("response:finished", "marketing", 1), ("response:finished", "operaciones", 2),
    ]
    assert all(e.part == 2 and e.event_type == "progress" and e.created_at is not None for e in events)
    assert ticket_of(engine, ticket_id).status == "under_evaluation"           # the normal work still happened


def test_the_pipeline_runs_inside_a_trace_for_this_ticket_and_it_is_switched_off_afterwards(engine, monkeypatch):
    seen = {}

    def fake(ticket_id, metadata, inputs, on_progress=None):
        tracer = rfp_trace.active()
        seen.update({"ticket": tracer.ticket_id, "part": tracer.part, "prefix": tracer.prefix})
        return STATE

    monkeypatch.setattr(rfp_routes, "run_response", fake)
    ticket_id = add_ticket(engine, status="drafting")
    REAL_PROCESS_GENERATION(ticket_id)
    assert seen == {"ticket": ticket_id, "part": 2, "prefix": "response"}
    assert rfp_trace.active() is None


def test_a_trace_that_cannot_be_saved_never_stops_the_drafts(monkeypatch):
    engine = make_engine(monkeypatch, with_events=False)           # no rfp_events table: every save fails

    def fake(ticket_id, metadata, inputs, on_progress=None):
        on_progress("marketing", "drafting", 1)
        return STATE

    monkeypatch.setattr(rfp_routes, "run_response", fake)
    ticket_id = add_ticket(engine, status="drafting")
    REAL_PROCESS_GENERATION(ticket_id)
    assert ticket_of(engine, ticket_id).status == "under_evaluation"      # the sections were still saved


# --- Part 1: intake ------------------------------------------------------------------------------

def test_intake_runs_inside_a_trace_for_this_ticket_and_it_is_switched_off_afterwards(engine, monkeypatch):
    seen = {}

    def fake(pdf, ticket_id=None):
        tracer = rfp_trace.active()
        seen.update({"ticket": tracer.ticket_id, "part": tracer.part, "prefix": tracer.prefix})
        raise RuntimeError("stop here: only the wiring is being checked")

    monkeypatch.setattr(rfp_routes, "run_intake", fake)
    ticket_id = add_ticket(engine, status="analyzing")
    rfp_routes.process_ticket(ticket_id)
    assert seen == {"ticket": ticket_id, "part": 1, "prefix": "intake"}
    assert rfp_trace.active() is None
    assert ticket_of(engine, ticket_id).status == "failed"                # the normal crash handling still ran


# --- the store ------------------------------------------------------------------------------------

def test_the_store_saves_every_field_of_an_event(engine):
    ticket_id = add_ticket(engine)
    rfp_trace_store.store_event({
        "ticket_id": ticket_id, "part": 1, "agent": "intake:classify", "event_type": "node_finished",
        "subject": None, "input": {"language": "en"}, "output": {"is_rfp": True}, "actor": None,
        "timestamp": "2026-10-02T17:33:25.123456",
    })
    (event,) = events_of(engine, ticket_id)
    assert (event.part, event.agent, event.event_type) == (1, "intake:classify", "node_finished")
    assert event.input_data == {"language": "en"} and event.output_data == {"is_rfp": True}
    assert event.created_at.isoformat() == "2026-10-02T17:33:25.123456"


def test_the_store_ignores_events_that_belong_to_no_ticket(engine):
    rfp_trace_store.store_event({"ticket_id": None, "part": 2, "agent": "x", "event_type": "node_finished",
                                 "input": {}, "output": {}, "timestamp": "2026-10-02T17:33:25"})
    with Session(engine) as db:
        assert db.exec(select(RfpEvent)).all() == []
