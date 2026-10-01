"""
tests/pipelines/test_rfp_approval_models.py -- the three Part 3 tables
(services/api/rfp_models.py): approvals, the event log, the final document.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from rfp_models import (  # noqa: E402
    RfpApproval, RfpEvent, RfpFinalDocument, RfpTicket,
    STATUS_DONE, STATUS_WAITING_FOR_APPROVAL,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(
        engine,
        tables=[RfpTicket.__table__, RfpApproval.__table__, RfpEvent.__table__, RfpFinalDocument.__table__],
    )
    with Session(engine) as session:
        ticket = RfpTicket(original_filename="a.pdf", raw_pdf_path="x")
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        session.info["ticket_id"] = ticket.id
        yield session


def test_the_part_3_statuses_are_the_ones_in_context():
    assert STATUS_WAITING_FOR_APPROVAL == "waiting_for_approval"
    assert STATUS_DONE == "done"


def test_an_approval_starts_pending_and_stores_estimates_as_json(db):
    tid = db.info["ticket_id"]
    db.add(RfpApproval(ticket_id=tid, subject="procurement", approver="Lucia Fernandez",
                       estimates={"ingredient_cost_per_cover_usd": 4.5}))
    db.commit()
    row = db.exec(select(RfpApproval)).one()
    assert row.status == "pending" and row.revision_count == 0 and row.decided_at is None
    assert row.estimates == {"ingredient_cost_per_cover_usd": 4.5}


def test_a_ticket_has_only_one_approval_per_approver(db):
    tid = db.info["ticket_id"]
    db.add(RfpApproval(ticket_id=tid, subject="marketing", approver="Camila Ospina"))
    db.commit()
    db.add(RfpApproval(ticket_id=tid, subject="marketing", approver="Camila Ospina"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_events_keep_agent_input_output_and_time_in_order(db):
    tid = db.info["ticket_id"]
    for agent in ("classifier", "generator", "human"):
        db.add(RfpEvent(ticket_id=tid, part=1, agent=agent, event_type="node_finished",
                        input_data={"in": agent}, output_data={"out": agent}))
        db.commit()
    rows = db.exec(select(RfpEvent).order_by(RfpEvent.id)).all()
    assert [r.agent for r in rows] == ["classifier", "generator", "human"]
    assert all(r.created_at is not None and r.input_data and r.output_data for r in rows)


def test_a_ticket_has_one_final_document(db):
    tid = db.info["ticket_id"]
    db.add(RfpFinalDocument(ticket_id=tid, sections=[{"department_id": "marketing"}], markdown="# Proposal"))
    db.commit()
    assert db.exec(select(RfpFinalDocument)).one().sections == [{"department_id": "marketing"}]
    db.add(RfpFinalDocument(ticket_id=tid, markdown="# Again"))
    with pytest.raises(IntegrityError):
        db.commit()
