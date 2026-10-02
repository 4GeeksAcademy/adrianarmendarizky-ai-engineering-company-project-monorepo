"""
tests/pipelines/test_rfp_approval_graphs.py -- the approval graphs of Part 3
(data/pipelines/rfp_approval/): interruption and resume, one department waiting
without blocking another, the revision limit, arbitration from the CONTEXT
conflict triggers, the CEO step, restarts, and the trace.

No real model: revisions are written by a fake. The checkpoint is a real SQLite
file in a temporary folder, so pauses really survive a "restart" (a brand-new
ApprovalSystem on the same file).
"""

import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_approval import decisions, settings  # noqa: E402
from rfp_approval.checkpoint import make_checkpointer  # noqa: E402
from rfp_approval.reviser import make_loop_reviser  # noqa: E402
from rfp_approval.system import (  # noqa: E402
    AlreadyOpen, ApprovalSystem, NotWaiting, UnknownTicket, thread_id,
)
from rfp_intake import llm  # noqa: E402

SUNSET = {"client_name": "Sunset Bay Resorts, LLC", "rfp_id": "SBR-1", "budget_range": "$60,000\u2013$75,000 USD"}
ANDES = {"client_name": "Andes Tech Solutions", "rfp_id": None, "budget_range": None}
CLEAN = "- Setup takes at least 10 business days."
BAD = "- Kitchen setup takes 5 business days after signing."


class FakeReviser:
    """Stands in for Part 2's loop. Records every call; can return a scripted draft or crash."""

    def __init__(self, drafts=None, fail_first=0):
        self.calls = []
        self.drafts = list(drafts or [])
        self.fail_first = fail_first

    def __call__(self, subject, state):
        self.calls.append({"subject": subject, "previous": state["draft_content"], "feedback": state["feedback"]})
        if self.fail_first:
            self.fail_first -= 1
            raise RuntimeError("model is down")
        draft = self.drafts.pop(0) if self.drafts else f"## {subject} (revision {len(self.calls)})\n{CLEAN}"
        return {"draft_content": draft, "evaluation": {"overall_pass": True}, "error": None}


def drafts_for(*departments, **overrides):
    return {
        d: {"draft_content": overrides.get(d, f"## {d} draft\n{CLEAN}"), "evaluation": {"overall_pass": True}, "card": {}}
        for d in departments
    }


@pytest.fixture()
def build(tmp_path):
    def _build(reviser=None, events=None, db="approvals.db"):
        sink = events.append if events is not None else None
        return ApprovalSystem(make_checkpointer(tmp_path / db), reviser or FakeReviser(), sink)
    return _build


def approve(system, ticket, subject, who="manager@brasaland.test", **estimates):
    response = {"action": "approve"}
    if estimates:
        response["estimates"] = estimates
    return system.decide(ticket, subject, response, who)


def request_changes(system, ticket, subject, why="Please add the staffing plan details."):
    return system.decide(ticket, subject, {"action": "request_changes", "comments": why}, "manager@brasaland.test")


def values(system, ticket, subject):
    return system.subject_state(ticket, subject)["values"]


# --- the pause: interrupt, then resume exactly where it stopped -----------------------

def test_opening_a_ticket_pauses_every_department_at_its_approval(build):
    system = build()
    outcome = system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "procurement"))
    assert outcome["outcome"] == "waiting_for_approval"
    assert outcome["waiting_for"] == ["marketing", "operaciones", "procurement"]
    for subject in ("marketing", "operaciones", "procurement"):
        state = system.subject_state(1, subject)
        assert state["waiting"] is True and state["next"] == ("await_decision",)
        assert state["values"]["status"] == "pending" and state["values"]["approver"] == settings.APPROVERS[subject]


def test_the_approver_is_shown_the_draft_the_evaluation_and_how_many_revisions_are_left(build):
    system = build()
    system.open_ticket(1, ANDES, {"marketing": {"draft_content": "## Brand\n- Text.", "evaluation": {"overall_pass": True},
                                                "card": {"key_aspects": ["Exclusive concession"]}}})
    packet = values(system, 1, "marketing")["packet"]
    assert packet["draft_content"] == "## Brand\n- Text."
    assert packet["evaluation"] == {"overall_pass": True}
    assert packet["card"] == {"key_aspects": ["Exclusive concession"]}
    assert packet["revisions_left"] == settings.REVISION_LIMIT and packet["approver"] == "Camila Ospina"


def test_approving_one_department_leaves_the_others_waiting_and_unchanged(build):
    # The ticket's parallel test: approve B while A stays interrupted.
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "procurement"))
    before = values(system, 1, "marketing")

    outcome = approve(system, 1, "operaciones")

    assert values(system, 1, "operaciones")["status"] == "approved"
    assert system.subject_state(1, "operaciones")["waiting"] is False
    assert system.subject_state(1, "marketing")["waiting"] is True        # A is still interrupted
    assert values(system, 1, "marketing") == before                       # ...and untouched
    assert system.subject_state(1, "procurement")["waiting"] is True
    assert outcome["outcome"] == "waiting_for_approval" and outcome["document"] is None
    assert outcome["waiting_for"] == ["marketing", "procurement"]


def test_a_department_asking_for_changes_is_revised_while_another_is_still_waiting(build):
    # In one shared graph this was impossible (checked while designing this): here it works.
    reviser = FakeReviser()
    system = build(reviser)
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones"))

    request_changes(system, 1, "operaciones", "Add the peak season staffing plan please.")

    assert len(reviser.calls) == 1                                   # the revision really ran...
    assert system.subject_state(1, "marketing")["waiting"] is True   # ...while marketing never moved
    assert values(system, 1, "marketing")["revision_count"] == 0
    assert system.subject_state(1, "operaciones")["waiting"] is True
    assert values(system, 1, "operaciones")["revision_count"] == 1


def test_resuming_continues_from_the_pause_and_does_not_restart_the_other_departments(build):
    events = []
    system = build(events=events)
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "procurement"))
    prepares_after_open = [e for e in events if e["agent"] == "approval:prepare"]
    assert len(prepares_after_open) == 3

    approve(system, 1, "marketing")
    approve(system, 1, "operaciones")

    # approving two of them must not have re-run (and re-logged) anybody's "prepare" step
    assert len([e for e in events if e["agent"] == "approval:prepare"]) == 3


def test_the_pause_survives_a_restart(build):
    first = build(db="shared.db")
    first.open_ticket(1, ANDES, drafts_for("marketing", "operaciones"))
    approve(first, 1, "marketing")

    second = build(db="shared.db")          # a brand-new object on the same checkpoint file
    assert values(second, 1, "marketing")["status"] == "approved"
    assert second.subject_state(1, "operaciones")["waiting"] is True
    outcome = approve(second, 1, "operaciones")
    assert outcome["outcome"] == "done" and outcome["document"] is not None


def test_two_approvals_at_the_same_moment_are_both_recorded(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "procurement"))
    barrier = threading.Barrier(3)
    errors = []

    def go(subject):
        try:
            barrier.wait()
            approve(system, 1, subject)
        except Exception as error:  # pragma: no cover - reported by the assert below
            errors.append(repr(error))

    threads = [threading.Thread(target=go, args=(s,)) for s in ("marketing", "operaciones", "procurement")]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    assert {s: values(system, 1, s)["status"] for s in ("marketing", "operaciones", "procurement")} == {
        "marketing": "approved", "operaciones": "approved", "procurement": "approved"}


# --- a human's answer is checked before the graph sees it ----------------------------------

def test_an_invalid_answer_is_refused_and_nothing_changes(build):
    events = []
    system = build(events=events)
    system.open_ticket(1, ANDES, drafts_for("marketing"))
    seen = len(events)

    with pytest.raises(decisions.InvalidDecision):
        system.decide(1, "marketing", {"action": "approved"}, "x@y.test")
    with pytest.raises(decisions.InvalidDecision):
        system.decide(1, "marketing", {"action": "reject"}, "x@y.test")          # no reason

    assert system.subject_state(1, "marketing")["waiting"] is True
    assert values(system, 1, "marketing")["status"] == "pending"
    assert len(events) == seen                                                    # not even a log line


def test_only_an_approver_who_is_waiting_can_decide(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones"))
    approve(system, 1, "marketing")
    with pytest.raises(NotWaiting, match="not waiting for a decision"):
        approve(system, 1, "marketing")                                           # already decided
    with pytest.raises(UnknownTicket):
        approve(system, 1, "ceo")                                                 # never requested
    with pytest.raises(UnknownTicket):
        approve(system, 99, "marketing")                                          # no such ticket
    with pytest.raises(decisions.InvalidDecision, match="not an approver"):
        approve(system, 1, "finance")


def test_a_ticket_cannot_be_opened_twice_until_it_is_reset(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing"))
    with pytest.raises(AlreadyOpen):
        system.open_ticket(1, ANDES, drafts_for("marketing"))
    system.reset_ticket(1)
    assert system.subject_state(1, "marketing") is None
    system.open_ticket(1, ANDES, drafts_for("marketing"))
    assert system.subject_state(1, "marketing")["waiting"] is True


# --- requesting changes, and the limit ------------------------------------------------------

def test_requesting_changes_rewrites_the_draft_from_the_approvers_comments_and_asks_again(build):
    reviser = FakeReviser(drafts=["## Operations (rewritten)\n" + CLEAN])
    system = build(reviser)
    system.open_ticket(1, ANDES, drafts_for("operaciones", operaciones="## Operations (first)\n" + CLEAN))

    request_changes(system, 1, "operaciones", "The staffing plan for the peak season is missing.")

    call = reviser.calls[0]
    assert call["previous"].startswith("## Operations (first)")                    # it saw the old draft
    assert call["feedback"].startswith("Requested by manager@brasaland.test:")      # who asked is part of the feedback
    assert "The staffing plan for the peak season is missing." in call["feedback"]  # ...and the comments
    state = values(system, 1, "operaciones")
    assert state["draft_content"].startswith("## Operations (rewritten)")
    assert state["revision_count"] == 1 and state["status"] == "pending"
    assert state["packet"]["draft_content"].startswith("## Operations (rewritten)") and state["packet"]["revisions_left"] == 1
    assert system.subject_state(1, "operaciones")["waiting"] is True               # asked again
    approve(system, 1, "operaciones")
    assert values(system, 1, "operaciones")["status"] == "approved"


def test_asking_for_changes_too_many_times_rejects_the_section(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones"))
    for _ in range(settings.REVISION_LIMIT):
        outcome = request_changes(system, 1, "operaciones")
        assert outcome["outcome"] == "waiting_for_approval"
    outcome = request_changes(system, 1, "operaciones")      # one more than allowed

    state = values(system, 1, "operaciones")
    assert state["status"] == "rejected" and "more than 2 times" in state["rejected_reason"]
    assert state["revision_count"] == settings.REVISION_LIMIT
    assert outcome["outcome"] == "department_rejected" and outcome["rejected"] == ["operaciones"]
    assert outcome["document"] is None


def test_a_rejection_sends_the_ticket_back_with_the_reason(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones"))
    outcome = system.decide(1, "marketing", {"action": "reject", "comments": "This offer is not acceptable."}, "m@x.test")
    assert outcome["outcome"] == "department_rejected"
    assert values(system, 1, "marketing")["rejected_reason"] == "This offer is not acceptable."


def test_a_crash_while_rewriting_leaves_the_approval_exactly_where_it_was_and_it_can_be_continued(build):
    reviser = FakeReviser(fail_first=1)
    system = build(reviser)
    system.open_ticket(1, ANDES, drafts_for("operaciones"))

    with pytest.raises(RuntimeError, match="model is down"):
        request_changes(system, 1, "operaciones")

    state = system.subject_state(1, "operaciones")
    assert state["waiting"] is False and state["next"] == ("revise",)          # stopped at the step that failed
    with pytest.raises(NotWaiting):
        approve(system, 1, "operaciones")

    system.continue_subject(1, "operaciones")                                  # from the checkpoint, not from scratch
    assert system.subject_state(1, "operaciones")["waiting"] is True
    assert values(system, 1, "operaciones")["revision_count"] == 1
    assert len(reviser.calls) == 2


# --- arbitration: the CONTEXT section 7 triggers --------------------------------------------

def test_setup_sla_breach_is_settled_by_the_arbiters_rule_and_the_section_is_sent_back(build):
    reviser = FakeReviser()
    events = []
    system = build(reviser, events=events)

    outcome = system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", operaciones="## Ops\n" + BAD))

    assert outcome["outcome"] == "changes_forced"
    assert outcome["resolutions"][0]["trigger"] == "setup-sla-breach"
    assert outcome["resolutions"][0]["decided_by"] == "Felipe Guerrero"
    assert list(outcome["forced"]) == ["operaciones"]
    assert "Arbitration setup-sla-breach (arbiter: Felipe Guerrero)" in reviser.calls[0]["feedback"]
    state = values(system, 1, "operaciones")
    assert state["revision_count"] == 1 and state["acted_by"] == "arbiter: Felipe Guerrero"
    assert system.subject_state(1, "operaciones")["waiting"] is True           # rewritten, waiting for its owner again
    assert system.subject_state(1, "marketing")["waiting"] is True             # marketing was not touched
    assert any(e["event_type"] == "arbitration" for e in events)


def test_a_breach_in_another_department_escalates_to_camila(build):
    system = build()
    outcome = system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "training", training="## T\n" + BAD))
    assert outcome["resolutions"][0]["decided_by"] == "Camila Ospina"
    assert list(outcome["forced"]) == ["training"]


def test_repeated_forced_changes_hit_the_same_revision_limit(build):
    reviser = FakeReviser(drafts=["## Ops\n" + BAD] * 10)      # the rewrite keeps the problem
    system = build(reviser)
    outcome = system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", operaciones="## Ops\n" + BAD))
    for _ in range(settings.REVISION_LIMIT):
        assert outcome["outcome"] == "changes_forced"
        outcome = system.coordinate(1)
    assert outcome["outcome"] == "department_rejected"          # an arbitration loop cannot run forever
    assert outcome["rejected"] == ["operaciones"]               # and the outcome says so
    assert "more than 2 times" in values(system, 1, "operaciones")["rejected_reason"]


def _approve_with_numbers(system, cost, price):
    approve(system, 1, "procurement", ingredient_cost_per_cover_usd=cost)
    return approve(system, 1, "operaciones", price_per_cover_usd=price)


def test_cost_vs_feasibility_pauses_for_the_named_arbiter(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("procurement", "operaciones"))

    outcome = _approve_with_numbers(system, cost=12.0, price=10.0)

    assert outcome["outcome"] == "arbitration_pending"
    assert outcome["arbitration"]["arbiter"] == "Camila Ospina"
    assert outcome["arbitration"]["choices"] == ["raise_price", "reduce_scope"]
    assert outcome["arbitration"]["details"]["ingredient_cost_per_cover_usd"] == 12.0
    assert outcome["document"] is None
    # nothing new is decided while she has not answered
    assert system.coordinate(1)["outcome"] == "arbitration_pending"


def test_the_arbiters_answer_is_checked_and_then_sends_both_sections_back(build):
    reviser = FakeReviser()
    system = build(reviser)
    system.open_ticket(1, ANDES, drafts_for("procurement", "operaciones"))
    _approve_with_numbers(system, cost=12.0, price=10.0)

    with pytest.raises(decisions.InvalidDecision):
        system.answer_arbitration(1, "cost-vs-feasibility", {"choice": "ignore it", "comments": "Not a choice."}, "c@x.test")
    with pytest.raises(decisions.InvalidDecision, match="settled by its rule"):
        system.answer_arbitration(1, "setup-sla-breach", {"choice": "raise_price", "comments": "Wrong trigger."}, "c@x.test")

    outcome = system.answer_arbitration(
        1, "cost-vs-feasibility", {"choice": "raise_price", "comments": "The margin needs it."}, "camila@brasaland.test")

    assert outcome["outcome"] == "changes_forced"
    assert outcome["resolutions"][0]["choice"] == "raise_price"
    assert outcome["resolutions"][0]["acted_by"] == "camila@brasaland.test"
    assert sorted(outcome["forced"]) == ["operaciones", "procurement"]
    for subject in ("operaciones", "procurement"):
        state = values(system, 1, subject)
        assert state["status"] == "pending" and state["estimates"] == {}      # the old numbers are gone
        assert system.subject_state(1, subject)["waiting"] is True
    assert "Raise the price" in reviser.calls[0]["feedback"]
    # with realistic numbers the conflict is gone and the ticket finishes
    outcome = _approve_with_numbers(system, cost=4.0, price=10.0)
    assert outcome["outcome"] == "done"


def test_cost_numbers_that_fit_never_pause_for_an_arbiter(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("procurement", "operaciones"))
    assert _approve_with_numbers(system, cost=4.0, price=10.0)["outcome"] == "done"


# --- the CEO ---------------------------------------------------------------------------------------

def test_above_50000_usd_the_ceo_must_approve_before_the_final_document(build):
    system = build()
    system.open_ticket(1, SUNSET, drafts_for("marketing", "operaciones"))
    approve(system, 1, "marketing")
    outcome = approve(system, 1, "operaciones")

    assert outcome["outcome"] == "waiting_for_ceo" and outcome["document"] is None
    assert outcome["waiting_for"] == ["ceo"]
    assert system.subject_state(1, "ceo")["waiting"] is True
    assert values(system, 1, "ceo")["approver"] == "Mariana Restrepo"
    assert any(r["trigger"] == "ceo-threshold" for r in outcome["resolutions"])

    outcome = system.decide(1, "ceo", {"action": "approve", "comments": "Good margin."}, "mariana@brasaland.test")
    assert outcome["outcome"] == "done"
    document = outcome["document"]
    assert [a["subject"] for a in document["approvals"]] == ["marketing", "operaciones", "ceo"]
    assert document["total_estimated_value"]["usd_high"] == 75000


def test_the_ceo_is_not_asked_before_every_department_has_approved(build):
    system = build()
    system.open_ticket(1, SUNSET, drafts_for("marketing", "operaciones"))
    approve(system, 1, "marketing")
    assert system.subject_state(1, "ceo") is None


def test_when_the_ceo_rejects_there_is_no_final_document(build):
    system = build()
    system.open_ticket(1, SUNSET, drafts_for("marketing", "operaciones"))
    approve(system, 1, "marketing")
    approve(system, 1, "operaciones")
    outcome = system.decide(1, "ceo", {"action": "reject", "comments": "The margin is too thin."}, "mariana@brasaland.test")
    assert outcome["outcome"] == "ceo_rejected" and outcome["document"] is None


def test_the_ceo_cannot_ask_for_changes(build):
    system = build()
    system.open_ticket(1, SUNSET, drafts_for("marketing", "operaciones"))
    approve(system, 1, "marketing")
    approve(system, 1, "operaciones")
    with pytest.raises(decisions.InvalidDecision):
        system.decide(1, "ceo", {"action": "request_changes", "comments": "Change the pricing please."}, "m@x.test")


def test_no_budget_means_no_ceo_step_and_the_document_is_made_by_itself(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "procurement"))
    approve(system, 1, "marketing")
    approve(system, 1, "procurement")
    outcome = approve(system, 1, "operaciones")
    assert outcome["outcome"] == "done"
    assert system.subject_state(1, "ceo") is None
    assert outcome["document"]["total_estimated_value"] is None
    assert [a["approver"] for a in outcome["document"]["approvals"]] == ["Camila Ospina", "Felipe Guerrero", "Lucia Fernandez"]


# --- the final document only appears when everything is in ----------------------------------

def test_no_document_is_made_until_the_last_approval(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing", "operaciones", "procurement", "training"))
    for subject in ("marketing", "operaciones", "procurement"):
        assert approve(system, 1, subject)["document"] is None
    assert approve(system, 1, "training")["document"] is not None


# --- isolation, trace, and the real Part 2 loop -----------------------------------------------

def test_threads_are_namespaced_by_ticket_and_approver(build):
    assert thread_id(12, "operaciones") == "rfp-12:operaciones"
    assert thread_id(12, "ceo") == "rfp-12:ceo"
    system = build()
    system.open_ticket(1, ANDES, drafts_for("marketing"))
    system.open_ticket(2, ANDES, drafts_for("marketing"))
    outcome = approve(system, 1, "marketing")
    assert outcome["outcome"] == "done"
    assert values(system, 2, "marketing")["status"] == "pending"               # ticket 2 did not share ticket 1's checkpoint
    assert system.subject_state(2, "marketing")["waiting"] is True


def test_every_node_execution_is_logged_with_agent_input_output_and_time(build):
    events = []
    system = build(events=events)
    system.open_ticket(1, ANDES, drafts_for("marketing"))
    approve(system, 1, "marketing", who="camila@brasaland.test")

    assert events, "nothing was logged"
    for event in events:
        assert event["agent"] and event["timestamp"] and "input" in event and "output" in event
    agents = [e["agent"] for e in events]
    for expected in ("approval:prepare", "human:await_decision", "approval:approve", "approval:detect_conflicts"):
        assert expected in agents
    human = next(e for e in events if e["event_type"] == "human_decision")
    assert human["actor"] == "camila@brasaland.test" and human["output"]["action"] == "approve"
    assert human["subject"] == "marketing"
    # the same events are kept in the graph's own state
    in_state = [e["agent"] for e in values(system, 1, "marketing")["trace"]]
    assert in_state == ["approval:prepare", "human:await_decision", "approval:approve"]


def test_long_text_in_an_event_is_cut_so_the_trace_stays_readable(build):
    events = []
    system = build(events=events)
    system.open_ticket(1, ANDES, drafts_for("marketing", marketing="## Brand\n" + "word " * 500))
    prepare = next(e for e in events if e["agent"] == "approval:prepare")
    assert len(json.dumps(prepare["output"])) < 2000


def test_a_sink_that_fails_never_stops_the_workflow(build):
    def broken(event):
        raise RuntimeError("database is down")
    system = ApprovalSystem(make_checkpointer(":memory:"), FakeReviser(), broken)
    system.open_ticket(1, ANDES, drafts_for("marketing"))
    assert approve(system, 1, "marketing")["outcome"] == "done"


def test_the_real_part_2_loop_rewrites_a_draft_from_the_approvers_comments(build, monkeypatch):
    ops_draft = (
        "## Operations and Delivery\n"
        "- Brasaland will run a concession stand at each of the 3 resort properties.\n"
        "- Kitchen setup takes 10 business days after signing.\n"
        "- The contract value is $60,000 USD (240,000,000 COP) per year."
    )
    prompts = []

    def stub_model(prompt, *, system=None):
        if "drafting one section" in system:
            prompts.append(prompt)
            return ops_draft
        if "relevance checker" in system:
            return json.dumps({"missing": []})
        return json.dumps({"competitors": []})

    monkeypatch.setattr(llm, "call_generation_llm", stub_model)
    context = {"metadata": SUNSET, "key_aspects": ["Concession stand at each of the 3 resorts."], "open_questions": []}
    system = build(make_loop_reviser(lambda ticket_id, subject: context))
    system.open_ticket(1, SUNSET, drafts_for("operaciones", operaciones="## Operations\n- Old text."))

    request_changes(system, 1, "operaciones", "Add the number of stands and the setup time please.")

    assert len(prompts) == 1
    assert "- Old text." in prompts[0]                                                  # it saw the draft the approver saw
    assert "Add the number of stands and the setup time please." in prompts[0]          # ...and the comments
    state = values(system, 1, "operaciones")
    assert state["draft_content"] == ops_draft
    assert state["evaluation"]["overall_pass"] is True                                  # re-evaluated by the Part 2 evaluators
    assert system.subject_state(1, "operaciones")["waiting"] is True


def test_an_arbiters_answer_is_refused_when_no_arbitration_is_waiting(build):
    system = build()
    system.open_ticket(1, ANDES, drafts_for("procurement", "operaciones"))
    with pytest.raises(NotWaiting, match="No arbitration is waiting"):
        system.answer_arbitration(
            1, "cost-vs-feasibility", {"choice": "raise_price", "comments": "Nothing to decide yet."}, "c@x.test")
