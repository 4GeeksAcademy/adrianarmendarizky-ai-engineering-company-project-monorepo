"""
tests/pipelines/test_rfp_api.py -- tests for the RFP intake API
(services/api/routes/rfp.py).

Nothing real is touched: the database is a throwaway in-memory SQLite, the
pipeline (run_intake) is replaced by a fake, and login is switched off.
"""

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
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import database  # noqa: E402
import routes.rfp as rfp_routes  # noqa: E402

# The `client` fixture below replaces rfp_routes.process_ticket with a
# do-nothing function. Keep the real one here for tests that need it.
REAL_PROCESS_TICKET = rfp_routes.process_ticket
from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from rfp_models import DepartmentSection, RfpMetadata, RfpTicket  # noqa: E402

READABILITY = {"word_count": 221, "flesch_kincaid": 12.4, "gunning_fog": 12.1, "readability_note": None}

COMPLETE_STATE = {
    "status": "intake_complete",
    "language": "en",
    "readability": READABILITY,
    "metadata": {
        "rfp_id": "SBR-1", "client_name": "Sunset Bay Resorts", "location": "Florida",
        "service_type": "concession", "scope": "3 resorts", "deadline": "Sep 2, 2026",
        "budget_range": None,
    },
    "departments_needed": ["marketing", "operaciones"],
    "missing_fields": ["budget_range"],
    "sections": {
        "marketing": {"key_aspects": ["Exclusive concession."], "open_questions": ["Brand rules?"]},
        "operaciones": {"key_aspects": ["3 stands."], "open_questions": []},
    },
    "sales_summary": {"overview": "Sunset Bay wants a concession."},
}


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(
        eng, tables=[RfpTicket.__table__, RfpMetadata.__table__, DepartmentSection.__table__]
    )
    monkeypatch.setattr(database, "engine", eng)
    return eng


def add_ticket(engine, status="analyzing"):
    with Session(engine) as db:
        ticket = RfpTicket(original_filename="a.pdf", raw_pdf_path="rfp-requests/x.pdf", status=status)
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket.id


def fake_pipeline(monkeypatch, state=None, error=None):
    def fake(pdf_path, ticket_id=None):
        if error:
            raise error
        return state
    monkeypatch.setattr(rfp_routes, "run_intake", fake)


def get_ticket(engine, ticket_id):
    with Session(engine) as db:
        return db.get(RfpTicket, ticket_id)


# --- saving results -----------------------------------------------------

def test_finished_run_saves_ticket_metadata_sections_and_summary(engine, monkeypatch):
    fake_pipeline(monkeypatch, COMPLETE_STATE)
    ticket_id = add_ticket(engine)
    rfp_routes.process_ticket(ticket_id)

    ticket = get_ticket(engine, ticket_id)
    assert ticket.status == "intake_complete"
    assert ticket.rfp_id == "SBR-1"
    assert ticket.sales_summary == {"overview": "Sunset Bay wants a concession."}
    with Session(engine) as db:
        metadata = db.exec(select(RfpMetadata)).one()
        sections = db.exec(select(DepartmentSection)).all()
    assert metadata.client_name == "Sunset Bay Resorts"
    assert metadata.missing_fields == ["budget_range"]
    assert metadata.word_count == 221
    assert {s.department_id for s in sections} == {"marketing", "operaciones"}


def test_discarded_run_saves_the_reason_and_no_sections(engine, monkeypatch):
    state = {"status": "discarded", "is_rfp": False, "discard_reason": "General franchise question.",
             "language": "es", "readability": {**READABILITY, "flesch_kincaid": None}}
    fake_pipeline(monkeypatch, state)
    ticket_id = add_ticket(engine)
    rfp_routes.process_ticket(ticket_id)

    ticket = get_ticket(engine, ticket_id)
    assert ticket.status == "discarded"
    assert ticket.discard_reason == "General franchise question."
    with Session(engine) as db:
        assert db.exec(select(RfpMetadata)).one().language == "es"
        assert db.exec(select(DepartmentSection)).all() == []


def test_failed_run_saves_the_error_and_never_half_of_the_sections(engine, monkeypatch):
    state = {"status": "failed", "error": "worker 'training' failed: boom", "language": "en",
             "readability": READABILITY, "sections": {"marketing": {"key_aspects": ["x"], "open_questions": []}}}
    fake_pipeline(monkeypatch, state)
    ticket_id = add_ticket(engine)
    rfp_routes.process_ticket(ticket_id)

    ticket = get_ticket(engine, ticket_id)
    assert ticket.status == "failed"
    assert "boom" in ticket.error_message
    with Session(engine) as db:
        assert db.exec(select(DepartmentSection)).all() == []


def test_crash_while_processing_marks_the_ticket_failed(engine, monkeypatch):
    fake_pipeline(monkeypatch, error=RuntimeError("db exploded"))
    ticket_id = add_ticket(engine)
    rfp_routes.process_ticket(ticket_id)

    ticket = get_ticket(engine, ticket_id)
    assert ticket.status == "failed"
    assert "db exploded" in ticket.error_message


def test_startup_check_fails_tickets_stuck_on_analyzing(engine):
    stuck_1 = add_ticket(engine, "analyzing")
    stuck_2 = add_ticket(engine, "analyzing")
    done = add_ticket(engine, "intake_complete")
    rfp_routes.fail_interrupted_tickets()

    assert get_ticket(engine, stuck_1).status == "failed"
    assert get_ticket(engine, stuck_2).status == "failed"
    assert "restarted" in get_ticket(engine, stuck_1).error_message
    assert get_ticket(engine, done).status == "intake_complete"


# --- the endpoints ------------------------------------------------------

@pytest.fixture()
def client(engine, monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(rfp_routes.router)

    def _db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: object()
    monkeypatch.setattr(rfp_routes, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(rfp_routes, "process_ticket", lambda ticket_id: None)
    return TestClient(app)


def test_upload_returns_202_saves_the_file_and_creates_an_analyzing_ticket(client, engine, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(rfp_routes, "process_ticket", lambda ticket_id: started.append(ticket_id))

    response = client.post("/rfp/tickets", files={"file": ("rfp.pdf", b"%PDF-1.4 fake", "application/pdf")})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "analyzing"
    assert started == [body["ticket_id"]]
    assert len(list(tmp_path.glob("*.pdf"))) == 1
    ticket = get_ticket(engine, body["ticket_id"])
    assert ticket.original_filename == "rfp.pdf" and ticket.status == "analyzing"


@pytest.mark.parametrize("filename, content", [
    ("notes.txt", b"%PDF-1.4 fake"),   # wrong file name
    ("rfp.pdf", b"hello, not a pdf"),  # wrong content
    ("rfp.pdf", b""),                  # empty
])
def test_bad_uploads_are_rejected_and_nothing_is_saved(client, engine, tmp_path, filename, content):
    response = client.post("/rfp/tickets", files={"file": (filename, content, "application/pdf")})
    assert response.status_code == 400
    assert list(tmp_path.glob("*")) == []
    with Session(engine) as db:
        assert db.exec(select(RfpTicket)).all() == []


def test_too_large_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(rfp_routes, "MAX_UPLOAD_BYTES", 10)
    response = client.post("/rfp/tickets", files={"file": ("rfp.pdf", b"%PDF-1.4 " + b"x" * 50, "application/pdf")})
    assert response.status_code == 413


def test_get_ticket_returns_status_metadata_and_summary(client, engine, monkeypatch):
    fake_pipeline(monkeypatch, COMPLETE_STATE)
    ticket_id = add_ticket(engine)
    REAL_PROCESS_TICKET(ticket_id)

    body = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert body["status"] == "intake_complete"
    assert body["metadata"]["client_name"] == "Sunset Bay Resorts"
    assert body["sales_summary"]["overview"] == "Sunset Bay wants a concession."
    assert [s["department_id"] for s in body["sections"]] == ["marketing", "operaciones"]


def test_unknown_ticket_is_a_404(client):
    assert client.get("/rfp/tickets/999").status_code == 404


def test_list_shows_newest_first(client, engine):
    first = add_ticket(engine)
    second = add_ticket(engine)
    rows = client.get("/rfp/tickets").json()
    assert [r["ticket_id"] for r in rows] == [second, first]
