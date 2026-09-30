"""
tests/pipelines/test_rfp_graph.py -- tests for the synthesizer and for the
whole RFP intake graph (data/pipelines/rfp_intake/).

The real model is never called: one fake model answers every stage, and it
decides what to say by looking at which stage's instructions it was sent.
The PDF step is replaced too, so these tests don't need any PDF file.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake import graph, llm, synthesizer  # noqa: E402

DOC = (
    "Sunset Bay Resorts seeks a concession partner for 3 resorts in Florida. "
    "Budget $60,000-$75,000 USD. Proposals due Sep 2, 2026."
)
EXTRACT = "Sunset Bay Resorts seeks a concession partner for 3 resorts in Florida."
GOOD_OVERVIEW = "Sunset Bay Resorts wants a concession partner for 3 resorts in Florida."


def make_fake(*, is_rfp=True, departments=("marketing", "operaciones"),
              overview=GOOD_OVERVIEW, fail_workers=False, calls=None):
    calls = calls if calls is not None else []

    def fake(prompt, *, system=None):
        if "intake classifier" in system:
            calls.append("classifier")
            return json.dumps({"is_rfp": is_rfp, "reason": "Not a request for a proposal."})
        if "intake orchestrator" in system:
            calls.append("orchestrator")
            return json.dumps({
                "rfp_id": None, "client_name": "Sunset Bay Resorts", "location": "Florida",
                "service_type": "co-branded concession", "scope": "3 resorts",
                "deadline": "Sep 2, 2026", "budget_range": "$60,000-$75,000 USD",
                "departments": {d: {"reason": "Applies.", "extract": EXTRACT} for d in departments},
                "other_departments_mentioned": [],
            })
        if "specialist" in system:
            calls.append("worker")
            if fail_workers:
                raise RuntimeError("boom")
            return json.dumps({"key_aspects": ["Runs stands at 3 resorts."],
                               "open_questions": ["What are the peak hours?"]})
        calls.append("synthesizer")
        return json.dumps({"overview": overview})

    return fake


def setup(monkeypatch, **options):
    calls = []
    monkeypatch.setattr(llm, "call_generation_llm", make_fake(calls=calls, **options))
    monkeypatch.setattr(graph, "pdf_to_markdown", lambda path: DOC)
    return calls


def test_accepted_rfp_runs_all_stages_and_completes(monkeypatch):
    calls = setup(monkeypatch)
    state = graph.run_intake("fake.pdf", ticket_id=7)
    assert state["status"] == "intake_complete"
    assert state["ticket_id"] == 7
    assert state["language"] == "en"
    assert state["departments_needed"] == ["marketing", "operaciones"]
    assert set(state["sections"]) == {"marketing", "operaciones"}
    assert calls.count("worker") == 2
    assert calls[0] == "classifier" and calls[-1] == "synthesizer"


def test_sales_summary_lists_owners_in_fixed_order(monkeypatch):
    setup(monkeypatch)
    summary = graph.run_intake("fake.pdf")["sales_summary"]
    owners = [(d["department_id"], d["owner"]) for d in summary["departments"]]
    assert owners == [("marketing", "Camila Ospina"), ("operaciones", "Felipe Guerrero")]
    assert summary["overview"] == GOOD_OVERVIEW
    assert summary["overview_source"] == "model"
    assert summary["total_open_questions"] == 2


def test_only_the_departments_that_apply_get_a_worker(monkeypatch):
    calls = setup(monkeypatch, departments=("marketing", "operaciones", "procurement", "training"))
    state = graph.run_intake("fake.pdf")
    assert calls.count("worker") == 4
    assert set(state["sections"]) == {"marketing", "operaciones", "procurement", "training"}


def test_rejected_document_is_discarded_and_nothing_else_runs(monkeypatch):
    calls = setup(monkeypatch, is_rfp=False)
    state = graph.run_intake("fake.pdf")
    assert state["status"] == "discarded"
    assert state["discard_reason"] == "Not a request for a proposal."
    assert calls == ["classifier"]
    assert not state.get("sections") and not state.get("sales_summary")


def test_a_crashing_worker_makes_the_ticket_failed_not_stuck(monkeypatch):
    setup(monkeypatch, fail_workers=True)
    state = graph.run_intake("fake.pdf")
    assert state["status"] == "failed"
    assert "boom" in state["error"] and "worker" in state["error"]
    assert "sales_summary" not in state


def test_pdf_with_no_readable_text_fails_cleanly(monkeypatch):
    calls = setup(monkeypatch)
    monkeypatch.setattr(graph, "pdf_to_markdown", lambda path: "   ")
    state = graph.run_intake("scan.pdf")
    assert state["status"] == "failed"
    assert "No text could be read" in state["error"]
    assert calls == []  # the model was never called


def test_unusable_model_reply_in_the_classifier_fails_instead_of_discarding(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", lambda prompt, *, system=None: "Sure thing!")
    monkeypatch.setattr(graph, "pdf_to_markdown", lambda path: DOC)
    state = graph.run_intake("fake.pdf")
    assert state["status"] == "failed"
    assert state.get("is_rfp") is None


def test_overview_with_an_invented_number_is_replaced_by_the_template(monkeypatch):
    setup(monkeypatch, overview="Sunset Bay Resorts wants a 10 year deal.")
    summary = graph.run_intake("fake.pdf")["sales_summary"]
    assert summary["overview_source"] == "template"
    assert "10 year" not in summary["overview"]
    assert "Sunset Bay Resorts" in summary["overview"]


def test_final_status_rules():
    assert graph.final_status({"error": "x", "sales_summary": {"a": 1}}) == "failed"
    assert graph.final_status({"is_rfp": False}) == "discarded"
    assert graph.final_status({"is_rfp": True, "sales_summary": {"a": 1}}) == "intake_complete"
    assert graph.final_status({"is_rfp": True}) == "failed"


def test_build_department_list_skips_departments_that_did_not_run():
    sections = {"procurement": {"key_aspects": ["a"], "open_questions": []}}
    result = synthesizer.build_department_list(sections)
    assert [d["department_id"] for d in result] == ["procurement"]
    assert result[0]["owner"] == "Lucia Fernandez"
