"""
tests/pipelines/test_rfp_end_to_end.py -- the reproducible end-to-end run
(scripts/rfp_e2e.py) as part of the test suite.

The script takes one RFP through all three parts with scripted humans, through the real
API routes, the real approval graphs and Part 2's real loop. Here it runs with no network:

  - "seeded": the ticket starts as Parts 1 and 2 leave it, and all of Part 3 runs for real
  - "upload": the real upload route and background saves run, with the two pipelines
    (Part 1 and Part 2) replaced by fakes that leave the same traces

Reviewers can run the same thing by hand, with the real model, from services/api:
    uv run python ../../scripts/rfp_e2e.py --live
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

import rfp_e2e  # noqa: E402

DEPARTMENTS = ["marketing", "operaciones", "procurement", "training"]


def failed_checks(report):
    return [f"{c['name']} ({c['detail']})" for c in report["checks"] if not c["ok"]]


@pytest.fixture(scope="module")
def seeded():
    return rfp_e2e.run_end_to_end()


# --- the seeded path: Part 3 for real ----------------------------------------------------------

def test_every_consistency_check_passes(seeded):
    assert failed_checks(seeded) == []
    assert seeded["ok"] is True and len(seeded["checks"]) >= 14


def test_the_ticket_goes_from_under_evaluation_to_waiting_for_approval_to_done(seeded):
    seen = []
    for entry in seeded["timeline"]:
        if not seen or seen[-1] != entry["status"]:
            seen.append(entry["status"])
    assert seen == ["under_evaluation", "waiting_for_approval", "done"]
    assert seeded["ticket_final"] == {"status": "done", "error_message": None}


def test_every_scripted_human_acted_in_order_and_the_conflict_and_the_ceo_happened(seeded):
    steps = {s["n"]: s for s in seeded["steps"]}
    assert len(steps) == 9 and not any("skipped" in s or "error" in s for s in steps.values())
    assert [steps[n]["who"] for n in (1, 2, 3, 4, 5, 6, 7, 8, 9)] == [
        "training", "marketing", "operaciones", "operaciones", "procurement",
        "cost-vs-feasibility", "operaciones", "procurement", "ceo"]
    assert steps[5]["outcome"] == "arbitration_pending"          # the cost conflict paused the ticket
    assert steps[6]["outcome"] == "changes_forced"                # the named arbiter settled it
    assert steps[8]["outcome"] == "waiting_for_ceo"               # only now was the CEO asked
    assert steps[9]["outcome"] == "done"


def test_the_final_document_holds_every_department_the_approvals_and_the_value(seeded):
    document = seeded["final_document"]
    assert [s["department_id"] for s in document["sections"]] == DEPARTMENTS
    assert [a["subject"] for a in document["approvals"]] == DEPARTMENTS + ["ceo"]
    assert document["total_estimated_value"]["usd_high"] == 75000
    text = document["markdown"]
    assert text.startswith("# Proposal for Sunset Bay Resorts, LLC")
    for title in ("Brand and Commercial Terms", "Operations and Delivery", "Ingredient Costs and Supply",
                  "Training and Certification", "## Approvals"):
        assert title in text
    assert "Mariana Restrepo | CEO" in text
    # the rewrite after "ask for changes" is what got approved
    assert "The exact number of staff per stand" in text


def test_the_trace_records_each_human_decision_with_who_made_it(seeded):
    humans = [(e["subject"], e["output"]["action"]) for e in seeded["trace"] if e["event_type"] == "human_decision"]
    assert humans[:3] == [("training", "approve"), ("marketing", "approve"), ("operaciones", "request_changes")]
    assert humans[-1] == ("ceo", "approve")
    assert {e["actor"] for e in seeded["trace"] if e["event_type"] == "human_decision"} == {rfp_e2e.APPROVER_EMAIL}


def test_the_report_is_ready_to_paste_into_a_pull_request(seeded):
    text = rfp_e2e.render_report(seeded)
    for heading in ("## Input RFP", "## Ticket states", "## Simulated approvals", "## Final document",
                    "## Trace", "## Consistency checks"):
        assert heading in text
    assert "ALL CHECKS PASSED" in text and "FAIL:" not in text
    assert text.count("\n| ") > 20                                  # the tables are really there
    assert "arbiter chose raise_price" in text and "the arbiter (Camila Ospina)" in text


# --- the other plans and the failure paths ---------------------------------------------------------

def test_the_quick_plan_skips_the_rewrite_and_the_conflict():
    report = rfp_e2e.run_end_to_end(quick=True)
    assert failed_checks(report) == [] and len(report["steps"]) == 5
    names = " ".join(c["name"] for c in report["checks"])
    assert "rewrote the draft" not in names and "conflict was open" not in names


def test_a_step_the_workflow_refuses_stops_the_run_with_a_clear_message_and_puts_everything_back(monkeypatch):
    import database
    from rfp_intake import llm

    monkeypatch.setattr(rfp_e2e, "PLAN", [{"kind": "decide", "subject": "training", "body": {"action": "approved"}}])
    engine_before, model_before = database.engine, llm.call_generation_llm
    with pytest.raises(AssertionError, match="step 1 \\(training\\) failed: 422"):
        rfp_e2e.run_end_to_end()
    assert database.engine is engine_before and llm.call_generation_llm is model_before


def test_a_failed_check_is_reported_and_changes_the_verdict(seeded):
    broken = {**seeded, "checks": seeded["checks"] + [{"name": "A made-up failing check", "ok": False, "detail": "x"}]}
    broken["ok"] = all(c["ok"] for c in broken["checks"])
    text = rfp_e2e.render_report(broken)
    assert "SOME CHECKS FAILED" in text and "FAIL: A made-up failing check (x)" in text


def test_running_it_twice_in_one_process_gives_the_same_result(seeded):
    again = rfp_e2e.run_end_to_end()
    assert again["ok"] is True and again["ticket_id"] == seeded["ticket_id"]
    assert [s.get("outcome") for s in again["steps"]] == [s.get("outcome") for s in seeded["steps"]]


def test_the_command_line_exits_with_zero_when_everything_passed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["rfp_e2e.py", "--quick"])
    assert rfp_e2e.main() == 0
    assert "ALL CHECKS PASSED" in capsys.readouterr().out


# --- the upload path: the real routes, with Parts 1 and 2 faked --------------------------------------

def test_the_upload_path_runs_intake_generation_and_approval_through_the_real_routes(monkeypatch, tmp_path):
    import rfp_trace
    import routes.rfp as rfp_routes
    from rfp_intake import llm

    def fake_run_intake(pdf_path, ticket_id=None):
        tracer = rfp_trace.active()                                # what the real graph leaves in the trace
        tracer._send(tracer._event("intake:convert", "node_finished", None, {"pdf_path": str(pdf_path)}, {"language": "en"}))
        return {
            "status": "intake_complete", "language": "en", "metadata": dict(rfp_e2e.SEED_METADATA),
            "readability": {"word_count": 221, "flesch_kincaid": 9.0, "gunning_fog": 10.0, "readability_note": None},
            "departments_needed": DEPARTMENTS, "missing_fields": [],
            "sections": {d: {"key_aspects": rfp_e2e.SEED_ASPECTS[d], "open_questions": rfp_e2e.SEED_QUESTIONS[d]}
                         for d in DEPARTMENTS},
            "sales_summary": {"overview": "Sunset Bay Resorts wants a co-branded concession at three resorts."},
        }

    def fake_run_response(ticket_id, metadata, inputs, on_progress=None):
        results = {}
        for d in DEPARTMENTS:
            for stage in ("drafting", "evaluating", "finished"):
                on_progress(d, stage, 1)
            results[d] = {
                "department_id": d, "status": "passed", "draft_content": rfp_e2e.DRAFTS[d][0], "iterations": 1,
                "history": [], "error": None,
                "evaluation_result": {
                    "department_id": d, "readability": {"pass": True, "score": None, "details": "ok"},
                    "relevance": {"pass": True, "missing_aspects": []},
                    "compliance": {"pass": True, "rule_ids": [], "violations": []},
                    "overall_pass": True, "feedback_for_generator": ""},
            }
        return {"status": "under_evaluation", "average_iterations": 1.0, "results": results, "error": None}

    monkeypatch.setattr(rfp_routes, "run_intake", fake_run_intake)
    monkeypatch.setattr(rfp_routes, "run_response", fake_run_response)
    monkeypatch.setattr(llm, "call_generation_llm", rfp_e2e.OfflineModel())   # only the rewrites ask the model
    pdf = tmp_path / "sample-rfp.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% a stand-in for the real sample RFP\n")

    report = rfp_e2e.run_end_to_end(live=True, pdf=pdf, load_env=False)

    assert failed_checks(report) == []
    assert report["mode"] == "live" and report["input"]["file"] == "sample-rfp.pdf"
    seen = []
    for entry in report["timeline"]:
        if not seen or seen[-1] != entry["status"]:
            seen.append(entry["status"])
    assert seen == ["intake_complete", "under_evaluation", "waiting_for_approval", "done"]
    parts = {e["part"] for e in report["trace"]}
    assert parts == {1, 2, 3}                                       # one trace from the PDF to the approvals
    first_parts = [e["part"] for e in report["trace"]]
    assert first_parts == sorted(first_parts)                       # Part 1, then Part 2, then Part 3


# --- the trace order check ------------------------------------------------------------------------------

def event(id, part, at):
    return {"id": id, "part": part, "created_at": at}


def test_a_trace_that_reads_from_part_1_to_part_3_in_order_passes():
    trace = [event(1, 1, "2026-10-02T17:00:00.000000"), event(2, 2, "2026-10-02T17:00:05.000000"),
             event(3, 3, "2026-10-02T17:01:00.000000")]
    assert rfp_e2e.trace_is_in_order(trace) is True


def test_events_from_departments_running_at_the_same_moment_may_be_a_few_milliseconds_out_of_order():
    trace = [event(1, 2, "2026-10-02T17:00:05.300000"), event(2, 2, "2026-10-02T17:00:05.100000"),
             event(3, 2, "2026-10-02T17:00:05.200000"), event(4, 3, "2026-10-02T17:00:09.000000")]
    assert rfp_e2e.trace_is_in_order(trace) is True


def test_a_trace_that_goes_back_in_time_or_back_a_part_or_loses_its_order_fails():
    assert rfp_e2e.trace_is_in_order([event(1, 2, "2026-10-02T17:00:10"), event(2, 2, "2026-10-02T17:00:05")]) is False
    assert rfp_e2e.trace_is_in_order([event(1, 3, "2026-10-02T17:00:01"), event(2, 2, "2026-10-02T17:00:02")]) is False
    assert rfp_e2e.trace_is_in_order([event(2, 1, "2026-10-02T17:00:01"), event(1, 1, "2026-10-02T17:00:02")]) is False
