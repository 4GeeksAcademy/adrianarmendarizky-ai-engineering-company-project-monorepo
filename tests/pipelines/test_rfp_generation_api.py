"""
tests/pipelines/test_rfp_generation_api.py -- tests for the Part 2 side of the
RFP API (services/api/routes/rfp.py): starting a draft, saving drafts and
evaluation results, following progress, and cleaning up after a crash or restart.

Nothing real is touched: the database is a throwaway in-memory SQLite, the
response pipeline (run_response) is replaced by a fake, and login is switched off.
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
from database import get_db  # noqa: E402
from dependencies import get_current_user  # noqa: E402
from rfp_models import DepartmentSection, RfpMetadata, RfpTicket  # noqa: E402

# The `client` fixture replaces process_generation with a do-nothing function
# so a request doesn't start real work. Keep the real one for tests that run it.
REAL_PROCESS_GENERATION = rfp_routes.process_generation

EVALUATION_KEYS = {
    "department_id", "readability", "relevance", "compliance",
    "overall_pass", "feedback_for_generator",
}


def passed_result(department_id, draft="## Draft\n- Text."):
    return {
        "department_id": department_id,
        "status": "passed",
        "draft_content": draft,
        "evaluation_result": {
            "department_id": department_id,
            "readability": {"pass": True, "score": 8.0, "details": "ok"},
            "relevance": {"pass": True, "missing_aspects": []},
            "compliance": {"pass": True, "rule_ids": [], "violations": []},
            "overall_pass": True,
            "feedback_for_generator": "",
        },
        "iterations": 1,
        "history": [{"iteration": 1, "overall_pass": True, "rule_ids": [],
                     "readability_score": 8.0, "missing_aspects": 0}],
        "error": None,
    }


def review_result(department_id, draft="## Last draft\n- Setup takes 5 business days."):
    result = passed_result(department_id, draft)
    result.update({"status": "needs_human_review", "iterations": 3})
    result["evaluation_result"].update({
        "overall_pass": False,
        "compliance": {"pass": False, "rule_ids": ["SETUP-MIN-10-DAYS"], "violations": [
            {"rule_id": "SETUP-MIN-10-DAYS", "message": "too short", "evidence": "Setup takes 5 business days."}]},
        "feedback_for_generator": "COMPLIANCE: fix the setup time.",
    })
    return result


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(
        eng, tables=[RfpTicket.__table__, RfpMetadata.__table__, DepartmentSection.__table__]
    )
    monkeypatch.setattr(database, "engine", eng)
    return eng


def add_ticket(engine, status="intake_complete", departments=("marketing", "operaciones")):
    """A ticket as Part 1 leaves it: metadata plus one section per department."""
    with Session(engine) as db:
        ticket = RfpTicket(original_filename="a.pdf", raw_pdf_path="rfp-requests/x.pdf",
                           status=status, rfp_id="SBR-1")
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        db.add(RfpMetadata(ticket_id=ticket.id, client_name="Sunset Bay Resorts", location="Florida",
                           service_type="concession", scope="3 resorts", deadline="Sep 2, 2026",
                           budget_range="$60,000 USD", language="en", word_count=221))
        for department in departments:
            db.add(DepartmentSection(ticket_id=ticket.id, department_id=department,
                                     key_aspects=[f"{department} aspect"],
                                     open_questions=[f"{department} question?"]))
        db.commit()
        return ticket.id


def sections_of(engine, ticket_id):
    with Session(engine) as db:
        rows = db.exec(select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)).all()
        return {s.department_id: s for s in rows}


def ticket_of(engine, ticket_id):
    with Session(engine) as db:
        return db.get(RfpTicket, ticket_id)


def set_sections(engine, ticket_id, evaluation_results, draft="## Draft"):
    with Session(engine) as db:
        for s in db.exec(select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)).all():
            s.evaluation_results = evaluation_results
            s.draft_content = draft
            db.add(s)
        db.commit()


def fake_response(monkeypatch, state=None, error=None, spy=None):
    def fake(ticket_id, metadata, inputs, on_progress=None):
        if spy is not None:
            spy.update({"ticket_id": ticket_id, "metadata": metadata, "inputs": inputs,
                        "on_progress": on_progress})
        if error:
            raise error
        return state
    monkeypatch.setattr(rfp_routes, "run_response", fake)


def never_reads_the_pdf(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("Part 2 must not run the PDF pipeline again")
    monkeypatch.setattr(rfp_routes, "run_intake", boom)


@pytest.fixture()
def client(engine, monkeypatch):
    app = FastAPI()
    app.include_router(rfp_routes.router)

    def _db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: object()
    monkeypatch.setattr(rfp_routes, "process_generation", lambda ticket_id: None)
    return TestClient(app)


# --- starting a draft -----------------------------------------------------------

def test_generate_returns_202_sets_drafting_and_queues_every_department(client, engine, monkeypatch):
    started = []
    monkeypatch.setattr(rfp_routes, "process_generation", lambda ticket_id: started.append(ticket_id))
    ticket_id = add_ticket(engine)

    response = client.post(f"/rfp/tickets/{ticket_id}/generate")

    assert response.status_code == 202
    assert response.json() == {"ticket_id": ticket_id, "status": "drafting"}
    assert started == [ticket_id]
    assert ticket_of(engine, ticket_id).status == "drafting"
    for section in sections_of(engine, ticket_id).values():
        assert section.evaluation_results == {"section_status": "running", "stage": "queued", "iteration": 0}
        assert section.draft_content is None


def test_unknown_ticket_is_a_404(client):
    assert client.post("/rfp/tickets/999/generate").status_code == 404


@pytest.mark.parametrize("status", ["analyzing", "discarded", "failed"])
def test_tickets_that_did_not_finish_intake_are_refused(client, engine, status):
    ticket_id = add_ticket(engine, status=status)
    response = client.post(f"/rfp/tickets/{ticket_id}/generate")
    assert response.status_code == 409
    assert status in response.json()["detail"]
    assert ticket_of(engine, ticket_id).status == status


def test_a_ticket_with_no_sections_is_refused(client, engine):
    ticket_id = add_ticket(engine, departments=())
    assert client.post(f"/rfp/tickets/{ticket_id}/generate").status_code == 409


def test_a_second_request_while_drafting_is_refused(client, engine):
    ticket_id = add_ticket(engine)
    assert client.post(f"/rfp/tickets/{ticket_id}/generate").status_code == 202
    second = client.post(f"/rfp/tickets/{ticket_id}/generate")
    assert second.status_code == 409
    assert "already being generated" in second.json()["detail"]


def test_under_evaluation_with_an_unfinished_section_counts_as_running(client, engine):
    ticket_id = add_ticket(engine, status="under_evaluation")
    set_sections(engine, ticket_id, {"section_status": "running", "stage": "evaluating", "iteration": 1})
    assert client.post(f"/rfp/tickets/{ticket_id}/generate").status_code == 409


@pytest.mark.parametrize("status, finished", [
    ("under_evaluation", "passed"),
    ("needs_human_review", "needs_human_review"),
])
def test_a_finished_ticket_can_be_generated_again(client, engine, status, finished):
    ticket_id = add_ticket(engine, status=status)
    set_sections(engine, ticket_id, {"section_status": finished, "iterations": 1})
    assert client.post(f"/rfp/tickets/{ticket_id}/generate").status_code == 202
    assert ticket_of(engine, ticket_id).status == "drafting"


# --- the background run ----------------------------------------------------------

def test_the_run_starts_from_part_1s_saved_results_and_never_reads_the_pdf(engine, monkeypatch):
    spy = {}
    fake_response(monkeypatch, {"status": "under_evaluation", "results": {}}, spy=spy)
    never_reads_the_pdf(monkeypatch)
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    assert spy["ticket_id"] == ticket_id
    assert spy["metadata"] == {
        "rfp_id": "SBR-1", "client_name": "Sunset Bay Resorts", "location": "Florida",
        "service_type": "concession", "scope": "3 resorts", "deadline": "Sep 2, 2026",
        "budget_range": "$60,000 USD",
    }
    assert spy["inputs"] == {
        "marketing": {"key_aspects": ["marketing aspect"], "open_questions": ["marketing question?"]},
        "operaciones": {"key_aspects": ["operaciones aspect"], "open_questions": ["operaciones question?"]},
    }


def test_every_section_is_saved_with_its_draft_and_a_structured_evaluation_result(engine, monkeypatch):
    state = {"status": "under_evaluation", "average_iterations": 1.0, "results": {
        "marketing": passed_result("marketing", "## Marketing draft"),
        "operaciones": passed_result("operaciones", "## Operations draft"),
    }}
    fake_response(monkeypatch, state)
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    ticket = ticket_of(engine, ticket_id)
    assert ticket.status == "under_evaluation" and ticket.error_message is None
    sections = sections_of(engine, ticket_id)
    assert sections["marketing"].draft_content == "## Marketing draft"
    assert sections["operaciones"].draft_content == "## Operations draft"
    for section in sections.values():
        evaluation = section.evaluation_results
        assert EVALUATION_KEYS <= set(evaluation)         # the shape the ticket asks for
        assert evaluation["overall_pass"] is True
        assert evaluation["section_status"] == "passed" and evaluation["iterations"] == 1
        assert "history" in evaluation and evaluation["error"] is None


def test_a_section_that_ran_out_of_drafts_keeps_its_last_draft_and_the_ticket_needs_review(engine, monkeypatch):
    state = {"status": "needs_human_review", "average_iterations": 2.0, "results": {
        "marketing": passed_result("marketing"),
        "operaciones": review_result("operaciones"),
    }}
    fake_response(monkeypatch, state)
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    assert ticket_of(engine, ticket_id).status == "needs_human_review"
    sections = sections_of(engine, ticket_id)
    assert set(sections) == {"marketing", "operaciones"}                  # nothing dropped
    failing = sections["operaciones"]
    assert failing.draft_content == "## Last draft\n- Setup takes 5 business days."
    assert failing.evaluation_results["overall_pass"] is False
    assert failing.evaluation_results["section_status"] == "needs_human_review"
    assert failing.evaluation_results["iterations"] == 3
    assert failing.evaluation_results["compliance"]["rule_ids"] == ["SETUP-MIN-10-DAYS"]
    assert "fix the setup time" in failing.evaluation_results["feedback_for_generator"]


def test_a_section_with_no_evaluation_is_saved_as_not_passed_with_its_error(engine, monkeypatch):
    broken = {"department_id": "operaciones", "status": "needs_human_review", "draft_content": "",
              "evaluation_result": None, "iterations": 1, "history": [], "error": "RuntimeError: model is down"}
    fake_response(monkeypatch, {"status": "needs_human_review", "results": {
        "marketing": passed_result("marketing"), "operaciones": broken}})
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    evaluation = sections_of(engine, ticket_id)["operaciones"].evaluation_results
    assert evaluation["overall_pass"] is False and evaluation["error"] == "RuntimeError: model is down"


def test_generation_that_crashes_goes_back_to_intake_complete_with_a_message(engine, monkeypatch):
    fake_response(monkeypatch, error=RuntimeError("graph exploded"))
    ticket_id = add_ticket(engine, status="drafting")
    set_sections(engine, ticket_id, {"section_status": "running", "stage": "drafting", "iteration": 1}, draft="half")

    REAL_PROCESS_GENERATION(ticket_id)

    ticket = ticket_of(engine, ticket_id)
    assert ticket.status == "intake_complete"
    assert "graph exploded" in ticket.error_message
    for section in sections_of(engine, ticket_id).values():
        assert section.draft_content is None and section.evaluation_results is None


def test_a_run_reported_as_failed_goes_back_to_intake_complete_too(engine, monkeypatch):
    fake_response(monkeypatch, {"status": "failed", "error": "response run crashed: boom", "results": {}})
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    ticket = ticket_of(engine, ticket_id)
    assert ticket.status == "intake_complete" and "boom" in ticket.error_message


# --- following progress in real time --------------------------------------------

def test_the_ticket_and_each_department_show_progress_as_the_pipeline_reports_it(engine, monkeypatch):
    seen = {}

    def fake(ticket_id, metadata, inputs, on_progress=None):
        on_progress("marketing", "drafting", 1)
        seen["while_drafting"] = (
            ticket_of(engine, ticket_id).status,
            sections_of(engine, ticket_id)["marketing"].evaluation_results,
        )
        on_progress("marketing", "evaluating", 1)
        seen["while_evaluating"] = (
            ticket_of(engine, ticket_id).status,
            sections_of(engine, ticket_id)["marketing"].evaluation_results,
        )
        on_progress("marketing", "finished", 1)   # the final save writes the finished section
        return {"status": "under_evaluation", "results": {
            "marketing": passed_result("marketing"), "operaciones": passed_result("operaciones")}}

    monkeypatch.setattr(rfp_routes, "run_response", fake)
    ticket_id = add_ticket(engine, status="drafting")

    REAL_PROCESS_GENERATION(ticket_id)

    assert seen["while_drafting"] == ("drafting", {"section_status": "running", "stage": "drafting", "iteration": 1})
    assert seen["while_evaluating"] == (
        "under_evaluation", {"section_status": "running", "stage": "evaluating", "iteration": 1})
    assert ticket_of(engine, ticket_id).status == "under_evaluation"


# --- what the API returns --------------------------------------------------------

def test_get_ticket_returns_drafts_evaluations_and_whether_it_is_still_running(client, engine, monkeypatch):
    fake_response(monkeypatch, {"status": "needs_human_review", "results": {
        "marketing": passed_result("marketing", "## Marketing draft"),
        "operaciones": review_result("operaciones")}})
    ticket_id = add_ticket(engine, status="drafting")
    REAL_PROCESS_GENERATION(ticket_id)

    body = client.get(f"/rfp/tickets/{ticket_id}").json()

    assert body["status"] == "needs_human_review"
    assert body["generation_running"] is False
    assert body["average_iterations"] == 2.0                      # (1 + 3) / 2
    by_department = {s["department_id"]: s for s in body["sections"]}
    assert by_department["marketing"]["draft_content"] == "## Marketing draft"
    assert EVALUATION_KEYS <= set(by_department["marketing"]["evaluation_results"])
    assert by_department["operaciones"]["evaluation_results"]["overall_pass"] is False


def test_get_ticket_says_it_is_running_while_drafts_are_being_written(client, engine):
    ticket_id = add_ticket(engine)
    client.post(f"/rfp/tickets/{ticket_id}/generate")
    body = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert body["status"] == "drafting" and body["generation_running"] is True
    assert body["average_iterations"] is None


def test_the_list_says_which_tickets_are_running(client, engine):
    running = add_ticket(engine)
    client.post(f"/rfp/tickets/{running}/generate")
    waiting = add_ticket(engine)
    rows = {r["ticket_id"]: r for r in client.get("/rfp/tickets").json()}
    assert rows[running]["generation_running"] is True
    assert rows[waiting]["generation_running"] is False


# --- a server restart --------------------------------------------------------------

def test_startup_check_puts_interrupted_drafts_back_to_intake_complete(engine):
    drafting = add_ticket(engine, status="drafting")
    cut_off = add_ticket(engine, status="under_evaluation")
    set_sections(engine, cut_off, {"section_status": "running", "stage": "evaluating", "iteration": 2}, draft="half")

    rfp_routes.fail_interrupted_tickets()

    for ticket_id in (drafting, cut_off):
        ticket = ticket_of(engine, ticket_id)
        assert ticket.status == "intake_complete"
        assert "restarted" in ticket.error_message and "generate them again" in ticket.error_message
        for section in sections_of(engine, ticket_id).values():
            assert section.draft_content is None and section.evaluation_results is None


def test_startup_check_leaves_finished_tickets_alone(engine):
    resting = add_ticket(engine, status="under_evaluation")
    set_sections(engine, resting, {"section_status": "passed", "iterations": 1}, draft="## Done")
    review = add_ticket(engine, status="needs_human_review")
    set_sections(engine, review, {"section_status": "needs_human_review", "iterations": 3}, draft="## Last")

    rfp_routes.fail_interrupted_tickets()

    assert ticket_of(engine, resting).status == "under_evaluation"
    assert ticket_of(engine, review).status == "needs_human_review"
    assert sections_of(engine, resting)["marketing"].draft_content == "## Done"


def test_startup_check_still_fails_tickets_stuck_in_intake(engine):
    stuck = add_ticket(engine, status="analyzing")
    rfp_routes.fail_interrupted_tickets()
    ticket = ticket_of(engine, stuck)
    assert ticket.status == "failed" and "restarted" in ticket.error_message
