"""
tests/pipelines/test_rfp_approval_api.py -- the Part 3 side of the RFP API
(services/api/routes/rfp_approval.py and services/api/rfp_approval_service.py):
sending a ticket for approval, each approver's decision, conflicts, the CEO, the
final document, the trace, and who is allowed to do what.

Nothing real is touched: the database is a throwaway in-memory SQLite, the
checkpoint is a real SQLite file in a temporary folder, rewrites are done by a
fake, and login is replaced by a user the test picks.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# security.py reads these the moment it is imported (see main.py's comment).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import database  # noqa: E402
import rfp_approval_service as service  # noqa: E402
import routes.rfp as rfp_routes  # noqa: E402
import routes.rfp_approval as approval_routes  # noqa: E402
from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from rfp_approval.checkpoint import make_checkpointer  # noqa: E402
from rfp_approval.system import ApprovalSystem  # noqa: E402
from rfp_models import (  # noqa: E402
    DepartmentSection, RfpApproval, RfpEvent, RfpFinalDocument, RfpMetadata, RfpTicket,
)
from user_models import Role  # noqa: E402


def make_user(email, role):
    """The routes only read .email and .role, so a plain object is enough."""
    return SimpleNamespace(email=email, role=role)


CLEAN = "- Setup takes at least 10 business days."
BAD = "- Kitchen setup takes 5 business days after signing."
SUNSET_BUDGET = "$60,000\u2013$75,000 USD"


class FakeReviser:
    def __init__(self, fail_first=0):
        self.calls = []
        self.fail_first = fail_first

    def __call__(self, subject, state):
        self.calls.append({"subject": subject, "feedback": state["feedback"]})
        if self.fail_first:
            self.fail_first -= 1
            raise RuntimeError("Could not rewrite the section: the model is down.")
        return {"draft_content": f"## {subject} (rewritten {len(self.calls)})\n{CLEAN}",
                "evaluation": {"overall_pass": True, "readability": {"pass": True, "score": 7.0},
                               "relevance": {"pass": True, "missing_aspects": []},
                               "compliance": {"pass": True, "rule_ids": [], "violations": []}},
                "error": None}


def passed_evaluation(department_id):
    return {
        "department_id": department_id, "section_status": "passed", "iterations": 1, "history": [], "error": None,
        "readability": {"pass": True, "score": 8.0, "details": "ok"},
        "relevance": {"pass": True, "missing_aspects": []},
        "compliance": {"pass": True, "rule_ids": [], "violations": []},
        "overall_pass": True, "feedback_for_generator": "",
    }


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng, tables=[
        RfpTicket.__table__, RfpMetadata.__table__, DepartmentSection.__table__,
        RfpApproval.__table__, RfpEvent.__table__, RfpFinalDocument.__table__,
    ])
    monkeypatch.setattr(database, "engine", eng)
    return eng


@pytest.fixture()
def reviser():
    return FakeReviser()


@pytest.fixture()
def checkpoint_file(tmp_path):
    return tmp_path / "approvals.db"


def build_system(checkpoint_file, reviser):
    return ApprovalSystem(make_checkpointer(checkpoint_file), reviser, sink=service._store_event)


@pytest.fixture()
def system(engine, checkpoint_file, reviser):
    made = build_system(checkpoint_file, reviser)
    service.use_system(made)
    yield made
    service.use_system(None)


@pytest.fixture()
def user():
    return {"current": make_user(email="manager@brasaland.test", role=Role.MANAGER)}


@pytest.fixture()
def client(engine, system, user):
    app = FastAPI()
    app.include_router(rfp_routes.router)
    app.include_router(approval_routes.router)

    def _db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user["current"]
    return TestClient(app)


def add_ticket(engine, status="under_evaluation", departments=("marketing", "operaciones"),
               budget=SUNSET_BUDGET, drafts=None):
    """A ticket as Part 2 leaves it: metadata plus one drafted, evaluated section per department."""
    drafts = drafts or {}
    with Session(engine) as db:
        ticket = RfpTicket(original_filename="a.pdf", raw_pdf_path="rfp-requests/x.pdf", status=status, rfp_id="SBR-1")
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        db.add(RfpMetadata(ticket_id=ticket.id, client_name="Sunset Bay Resorts, LLC", location="Florida",
                           service_type="concession", scope="3 resorts", deadline="Sep 2, 2026",
                           budget_range=budget, language="en", word_count=221))
        for department in departments:
            db.add(DepartmentSection(
                ticket_id=ticket.id, department_id=department,
                key_aspects=[f"{department} aspect"], open_questions=[f"{department} question?"],
                draft_content=drafts.get(department, f"## {department} draft\n{CLEAN}"),
                evaluation_results=passed_evaluation(department)))
        db.commit()
        return ticket.id


def ticket_of(engine, ticket_id):
    with Session(engine) as db:
        return db.get(RfpTicket, ticket_id)


def section_of(engine, ticket_id, department):
    with Session(engine) as db:
        return db.exec(select(DepartmentSection).where(
            DepartmentSection.ticket_id == ticket_id, DepartmentSection.department_id == department)).one()


def approval_rows(engine, ticket_id):
    with Session(engine) as db:
        return {a.subject: a for a in db.exec(select(RfpApproval).where(RfpApproval.ticket_id == ticket_id)).all()}


def send(client, ticket_id):
    return client.post(f"/rfp/tickets/{ticket_id}/send-for-approval")


def decide(client, ticket_id, subject, **body):
    return client.post(f"/rfp/tickets/{ticket_id}/approvals/{subject}", json=body)


def approve(client, ticket_id, subject, **body):
    return decide(client, ticket_id, subject, action="approve", **body)


def approvers_of(response):
    """The approvers in the answer to a POST (the list sits under "approvals")."""
    return {a["subject"]: a for a in response.json()["approvals"]["approvers"]}


def approvers_now(client, ticket_id):
    """The approvers as GET /approvals shows them."""
    body = client.get(f"/rfp/tickets/{ticket_id}/approvals").json()
    return {a["subject"]: a for a in body["approvers"]}


# --- sending a ticket for approval ----------------------------------------------------------

def test_sending_a_ticket_opens_one_pending_approval_per_department(client, engine):
    tid = add_ticket(engine, departments=("marketing", "operaciones", "procurement"))
    response = send(client, tid)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"]["outcome"] == "waiting_for_approval" and body["outcome"]["document_ready"] is False
    approvers = approvers_of(response)
    assert list(approvers) == ["marketing", "operaciones", "procurement"]
    assert all(a["waiting"] and a["status"] == "pending" for a in approvers.values())
    assert approvers["operaciones"]["approver"] == "Felipe Guerrero"
    assert ticket_of(engine, tid).status == "waiting_for_approval"
    rows = approval_rows(engine, tid)
    assert {s: r.status for s, r in rows.items()} == {"marketing": "pending", "operaciones": "pending", "procurement": "pending"}


def test_the_approver_sees_the_draft_the_evaluation_and_the_facts_it_came_from(client, engine):
    tid = add_ticket(engine, drafts={"marketing": "## Brand\n- Exclusive concession."})
    approver = approvers_of(send(client, tid))["marketing"]
    assert approver["draft_content"] == "## Brand\n- Exclusive concession."
    assert approver["evaluation"]["overall_pass"] is True
    assert approver["card"] == {"key_aspects": ["marketing aspect"], "open_questions": ["marketing question?"]}
    assert approver["revisions_left"] == 2


def test_only_a_ticket_with_finished_drafts_can_be_sent(client, engine):
    for status in ("intake_complete", "analyzing", "waiting_for_approval", "done", "discarded"):
        tid = add_ticket(engine, status=status)
        assert send(client, tid).status_code == 409, status
    assert send(client, 9999).status_code == 404


def test_a_ticket_whose_drafts_are_still_being_written_cannot_be_sent(client, engine):
    tid = add_ticket(engine, status="drafting")
    assert send(client, tid).status_code == 409


def test_a_section_with_no_draft_blocks_sending_and_says_which(client, engine):
    tid = add_ticket(engine, departments=("marketing", "operaciones"))
    with Session(engine) as db:
        section = db.exec(select(DepartmentSection).where(
            DepartmentSection.ticket_id == tid, DepartmentSection.department_id == "operaciones")).one()
        section.draft_content = None
        db.add(section)
        db.commit()
    response = send(client, tid)
    assert response.status_code == 409 and "operaciones" in response.json()["detail"]
    assert ticket_of(engine, tid).status == "under_evaluation"


def test_a_ticket_that_has_not_been_sent_shows_no_approvals(client, engine):
    tid = add_ticket(engine)
    body = client.get(f"/rfp/tickets/{tid}/approvals").json()
    assert body["started"] is False and body["approvers"] == [] and body["status"] == "under_evaluation"


def test_drafts_cannot_be_regenerated_while_approvals_are_in_progress(client, engine):
    tid = add_ticket(engine)
    send(client, tid)
    assert client.post(f"/rfp/tickets/{tid}/generate").status_code == 409


# --- deciding ----------------------------------------------------------------------------------

def test_one_approval_is_recorded_and_the_others_keep_waiting(client, engine):
    tid = add_ticket(engine, departments=("marketing", "operaciones", "procurement"), budget=None)
    send(client, tid)

    response = approve(client, tid, "operaciones", comments="Staffing plan looks right.")

    assert response.status_code == 200
    approvers = approvers_of(response)
    assert approvers["operaciones"]["status"] == "approved" and approvers["operaciones"]["acted_by"] == "manager@brasaland.test"
    assert approvers["marketing"]["waiting"] and approvers["procurement"]["waiting"]
    assert response.json()["outcome"]["waiting_for"] == ["marketing", "procurement"]
    assert ticket_of(engine, tid).status == "waiting_for_approval"
    row = approval_rows(engine, tid)["operaciones"]
    assert row.status == "approved" and row.acted_by == "manager@brasaland.test" and row.decided_at is not None
    ops = section_of(engine, tid, "operaciones")
    assert ops.approval_status == "approved" and ops.approver == "Felipe Guerrero" and ops.approved_at is not None
    assert section_of(engine, tid, "marketing").approval_status == "pending"


def test_only_managers_and_admins_can_record_an_approval(client, engine, user):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    user["current"] = make_user(email="someone@brasaland.test", role=Role.USER)
    response = approve(client, tid, "marketing")
    assert response.status_code == 403 and "managers and admins" in response.json()["detail"]
    assert approvers_now(client, tid)["marketing"]["status"] == "pending"
    for role in (Role.MANAGER, Role.ADMIN):
        user["current"] = make_user(email=f"{role.value}@brasaland.test", role=role)
    assert approve(client, tid, "marketing").status_code == 200       # (the admin, last)


def test_a_bad_answer_is_refused_with_a_message_and_changes_nothing(client, engine):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    for body in ({"action": "approved"}, {"action": "reject"}, {"action": "approve", "comment": "typo"}, {}):
        response = client.post(f"/rfp/tickets/{tid}/approvals/marketing", json=body)
        assert response.status_code == 422, body
        assert response.json()["detail"]
    assert approval_rows(engine, tid)["marketing"].status == "pending"
    assert decide(client, tid, "finance", action="approve").status_code == 422


def test_a_decision_cannot_be_made_twice_and_unknown_tickets_are_404(client, engine):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    assert approve(client, tid, "marketing").status_code == 200
    again = approve(client, tid, "marketing")
    assert again.status_code == 409 and "not waiting for a decision" in again.json()["detail"]
    assert approve(client, 9999, "marketing").status_code == 404
    assert approve(client, tid, "ceo").status_code == 404                 # the CEO was never asked


def test_a_ticket_that_is_not_waiting_for_approval_refuses_decisions(client, engine):
    tid = add_ticket(engine)
    response = approve(client, tid, "marketing")
    assert response.status_code == 409 and "not waiting for approval" in response.json()["detail"]


# --- requesting changes, rejecting, the limit -------------------------------------------------------

def test_requesting_changes_rewrites_the_draft_and_the_new_draft_is_saved(client, engine, reviser):
    tid = add_ticket(engine, budget=None)
    send(client, tid)

    response = decide(client, tid, "operaciones", action="request_changes",
                      comments="Please add the staffing plan for the peak season.")

    assert response.status_code == 200
    operaciones = approvers_of(response)["operaciones"]
    assert operaciones["waiting"] and operaciones["revision_count"] == 1 and operaciones["revisions_left"] == 1
    assert operaciones["draft_content"].startswith("## operaciones (rewritten 1)")
    assert "Please add the staffing plan for the peak season." in reviser.calls[0]["feedback"]
    saved = section_of(engine, tid, "operaciones")
    assert saved.draft_content.startswith("## operaciones (rewritten 1)")
    assert saved.evaluation_results["revisions_requested"] == 1 and saved.evaluation_results["overall_pass"] is True
    assert approval_rows(engine, tid)["operaciones"].revision_count == 1
    assert ticket_of(engine, tid).status == "waiting_for_approval"


def test_a_rejection_sends_the_ticket_back_with_the_reason_and_it_can_be_sent_again(client, engine):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    response = decide(client, tid, "marketing", action="reject", comments="This offer is not acceptable.")

    assert response.json()["outcome"]["outcome"] == "department_rejected"
    ticket = ticket_of(engine, tid)
    assert ticket.status == "needs_human_review" and "marketing" in ticket.error_message
    assert "This offer is not acceptable." in ticket.error_message
    assert section_of(engine, tid, "marketing").approval_status == "rejected"

    again = send(client, tid)                                           # a fresh round
    assert again.status_code == 200
    assert ticket_of(engine, tid).status == "waiting_for_approval" and ticket_of(engine, tid).error_message is None
    assert {r.status for r in approval_rows(engine, tid).values()} == {"pending"}


def test_asking_for_changes_too_many_times_rejects_the_section(client, engine):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    for _ in range(2):
        assert decide(client, tid, "operaciones", action="request_changes", comments="Please improve this section.").status_code == 200
    response = decide(client, tid, "operaciones", action="request_changes", comments="Please improve this section again.")
    assert response.json()["outcome"]["outcome"] == "department_rejected"
    ticket = ticket_of(engine, tid)
    assert ticket.status == "needs_human_review" and "more than 2 times" in ticket.error_message


def test_a_crash_while_rewriting_leaves_everything_as_it_was_and_it_can_be_continued(client, engine, reviser):
    reviser.fail_first = 1
    tid = add_ticket(engine, budget=None)
    send(client, tid)

    failed = decide(client, tid, "operaciones", action="request_changes", comments="Please add the staffing plan.")

    assert failed.status_code == 502 and "continue" in failed.json()["detail"]
    assert section_of(engine, tid, "operaciones").draft_content.startswith("## operaciones draft")   # not changed
    assert ticket_of(engine, tid).status == "waiting_for_approval"
    assert approve(client, tid, "operaciones").status_code == 409                                    # not waiting: mid-rewrite

    resumed = client.post(f"/rfp/tickets/{tid}/approvals/operaciones/continue")
    assert resumed.status_code == 200
    operaciones = approvers_of(resumed)["operaciones"]
    assert operaciones["waiting"] and operaciones["draft_content"].startswith("## operaciones (rewritten 2)")
    assert section_of(engine, tid, "operaciones").draft_content.startswith("## operaciones (rewritten 2)")


# --- finishing: the document, the CEO ----------------------------------------------------------------

def test_when_everyone_has_approved_the_document_is_made_and_the_ticket_is_done(client, engine):
    tid = add_ticket(engine, departments=("marketing", "operaciones", "procurement"), budget=None)
    send(client, tid)
    assert client.get(f"/rfp/tickets/{tid}/final-document").status_code == 404      # not yet
    approve(client, tid, "marketing")
    approve(client, tid, "procurement")
    response = approve(client, tid, "operaciones")

    assert response.json()["outcome"]["outcome"] == "done" and response.json()["outcome"]["document_ready"] is True
    assert "document" not in response.json()["outcome"]
    assert ticket_of(engine, tid).status == "done"
    document = client.get(f"/rfp/tickets/{tid}/final-document").json()
    assert [s["department_id"] for s in document["sections"]] == ["marketing", "operaciones", "procurement"]
    assert document["total_estimated_value"] is None
    assert "## marketing draft" in document["markdown"] and "Felipe Guerrero" in document["markdown"]
    with Session(engine) as db:
        assert db.exec(select(RfpFinalDocument)).one().ticket_id == tid


def test_above_50000_usd_the_ticket_stays_waiting_until_the_ceo_approves(client, engine):
    tid = add_ticket(engine, departments=("marketing", "operaciones"))               # $60,000-$75,000
    send(client, tid)
    approve(client, tid, "marketing")
    response = approve(client, tid, "operaciones")

    assert response.json()["outcome"]["outcome"] == "waiting_for_ceo"
    assert ticket_of(engine, tid).status == "waiting_for_approval"
    ceo = approvers_of(response)["ceo"]
    assert ceo["approver"] == "Mariana Restrepo" and ceo["waiting"]
    assert approval_rows(engine, tid)["ceo"].status == "pending"
    assert client.get(f"/rfp/tickets/{tid}/final-document").status_code == 404

    done = approve(client, tid, "ceo", comments="Good margin.")
    assert done.json()["outcome"]["outcome"] == "done" and ticket_of(engine, tid).status == "done"
    document = client.get(f"/rfp/tickets/{tid}/final-document").json()
    assert document["total_estimated_value"]["usd_high"] == 75000
    assert [a["subject"] for a in document["approvals"]] == ["marketing", "operaciones", "ceo"]


def test_when_the_ceo_rejects_the_ticket_goes_back_with_the_reason(client, engine):
    tid = add_ticket(engine, departments=("marketing", "operaciones"))
    send(client, tid)
    approve(client, tid, "marketing")
    approve(client, tid, "operaciones")
    response = decide(client, tid, "ceo", action="reject", comments="The margin is too thin.")
    assert response.json()["outcome"]["outcome"] == "ceo_rejected"
    ticket = ticket_of(engine, tid)
    assert ticket.status == "needs_human_review" and "The CEO" in ticket.error_message
    assert client.get(f"/rfp/tickets/{tid}/final-document").status_code == 404


# --- arbitration ----------------------------------------------------------------------------------------

def test_a_setup_breach_is_sent_back_by_the_arbiters_rule_as_soon_as_the_ticket_is_sent(client, engine, reviser):
    tid = add_ticket(engine, budget=None, drafts={"operaciones": "## Ops\n" + BAD})
    response = send(client, tid)
    assert response.json()["outcome"]["outcome"] == "changes_forced"
    assert response.json()["outcome"]["resolutions"][0]["decided_by"] == "Felipe Guerrero"
    assert "Arbitration setup-sla-breach (arbiter: Felipe Guerrero)" in reviser.calls[0]["feedback"]
    assert section_of(engine, tid, "operaciones").draft_content.startswith("## operaciones (rewritten 1)")
    assert ticket_of(engine, tid).status == "waiting_for_approval"


def _cost_conflict(client, engine):
    tid = add_ticket(engine, departments=("procurement", "operaciones"), budget=None)
    send(client, tid)
    approve(client, tid, "procurement", estimates={"ingredient_cost_per_cover_usd": 12.0})
    return tid, approve(client, tid, "operaciones", estimates={"price_per_cover_usd": 10.0})


def test_a_cost_conflict_waits_for_the_named_arbiter_and_is_shown(client, engine):
    tid, response = _cost_conflict(client, engine)
    assert response.json()["outcome"]["outcome"] == "arbitration_pending"
    arbitration = client.get(f"/rfp/tickets/{tid}/approvals").json()["arbitration"]
    assert arbitration["arbiter"] == "Camila Ospina" and arbitration["choices"] == ["raise_price", "reduce_scope"]
    assert ticket_of(engine, tid).status == "waiting_for_approval"
    assert approval_rows(engine, tid)["procurement"].estimates == {"ingredient_cost_per_cover_usd": 12.0}


def test_the_arbiters_answer_is_checked_and_then_both_sections_go_back(client, engine, user):
    tid, _ = _cost_conflict(client, engine)
    url = f"/rfp/tickets/{tid}/arbitration/cost-vs-feasibility"

    assert client.post(url, json={"choice": "ignore", "comments": "Not a real choice."}).status_code == 422
    assert client.post(f"/rfp/tickets/{tid}/arbitration/setup-sla-breach",
                       json={"choice": "raise_price", "comments": "Wrong trigger."}).status_code == 422
    user["current"] = make_user(email="x@brasaland.test", role=Role.USER)
    assert client.post(url, json={"choice": "raise_price", "comments": "The margin needs it."}).status_code == 403
    user["current"] = make_user(email="camila@brasaland.test", role=Role.MANAGER)

    response = client.post(url, json={"choice": "raise_price", "comments": "The margin needs it."})

    assert response.status_code == 200 and response.json()["outcome"]["outcome"] == "changes_forced"
    assert response.json()["outcome"]["resolutions"][0]["acted_by"] == "camila@brasaland.test"
    approvers = approvers_of(response)
    assert approvers["procurement"]["status"] == "pending" and approvers["procurement"]["estimates"] == {}
    assert approvers["operaciones"]["waiting"] and response.json()["approvals"]["arbitration"] is None
    assert approval_rows(engine, tid)["procurement"].estimates is None
    # with realistic numbers the ticket finishes
    approve(client, tid, "procurement", estimates={"ingredient_cost_per_cover_usd": 4.0})
    done = approve(client, tid, "operaciones", estimates={"price_per_cover_usd": 10.0})
    assert done.json()["outcome"]["outcome"] == "done"


def test_an_arbitration_answer_is_refused_when_nothing_is_waiting(client, engine):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    response = client.post(f"/rfp/tickets/{tid}/arbitration/cost-vs-feasibility",
                           json={"choice": "raise_price", "comments": "Nothing to decide yet."})
    assert response.status_code == 409


# --- the trace, and restarts ------------------------------------------------------------------------------

def test_the_trace_lists_every_step_in_order_with_who_did_it(client, engine):
    tid = add_ticket(engine, budget=None)
    other = add_ticket(engine, budget=None)
    send(client, tid)
    send(client, other)
    approve(client, tid, "marketing", comments="Fine.")

    trace = client.get(f"/rfp/tickets/{tid}/trace").json()

    assert [e["id"] for e in trace] == sorted(e["id"] for e in trace)
    agents = [e["agent"] for e in trace]
    assert agents.count("approval:prepare") == 2 and "approval:detect_conflicts" in agents
    human = next(e for e in trace if e["event_type"] == "human_decision")
    assert human["actor"] == "manager@brasaland.test" and human["subject"] == "marketing"
    assert human["output"]["action"] == "approve"
    assert all(e["created_at"] and "input" in e and "output" in e for e in trace)
    with Session(engine) as db:                                                  # ticket 2's events are kept apart
        assert {e.ticket_id for e in db.exec(select(RfpEvent)).all()} == {tid, other}
    assert len(client.get(f"/rfp/tickets/{tid}/trace?limit=3").json()) == 3


def test_approvals_survive_a_server_restart(client, engine, checkpoint_file, reviser):
    tid = add_ticket(engine, budget=None)
    send(client, tid)
    approve(client, tid, "marketing")

    service.use_system(build_system(checkpoint_file, reviser))                  # a brand-new ApprovalSystem

    approvers = approvers_now(client, tid)
    assert approvers["marketing"]["status"] == "approved" and approvers["operaciones"]["waiting"]
    done = approve(client, tid, "operaciones")
    assert done.json()["outcome"]["outcome"] == "done" and ticket_of(engine, tid).status == "done"


def test_a_trace_that_cannot_be_stored_never_stops_an_approval(client, engine, monkeypatch):
    tid = add_ticket(engine, budget=None)
    send(client, tid)

    def broken(event):
        raise RuntimeError("database is down")
    monkeypatch.setattr(service, "_store_event", broken)
    service.use_system(ApprovalSystem(make_checkpointer(":memory:"), FakeReviser(), sink=broken))
    # a different system, so open a fresh ticket on it
    other = add_ticket(engine, budget=None)
    assert send(client, other).status_code == 200
    assert approve(client, other, "marketing").status_code == 200
