"""
tests/pipelines/test_rfp_response_loop.py -- tests for the generator-evaluator
loop (data/pipelines/rfp_response/loop.py) and the response graph
(data/pipelines/rfp_response/graph.py).

The real model is never called. One scripted fake model plays every agent
(generators, relevance checker, competitor checker) and decides who is
asking by looking at the instructions it receives.
"""

import json
import re
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake import llm  # noqa: E402
from rfp_response import graph, loop, settings  # noqa: E402

METADATA = {
    "client_name": "Sunset Bay Resorts, LLC",
    "location": "Florida",
    "service_type": "co-branded concession",
    "scope": "3 resort properties",
    "deadline": "September 2, 2026",
    "budget_range": "$60,000\u2013$75,000 USD",
}
OPS_ASPECTS = ["OPS-ONLY: concession stand at each of the 3 resorts."]
MKT_ASPECTS = ["MKT-ONLY: exclusive co-branded menu item."]

OPS_GOOD = (
    "## Operations and Delivery\n"
    "- Brasaland will run a concession stand at each of the 3 resort properties.\n"
    "- Kitchen setup takes 10 business days after signing.\n"
    "- The contract value is $60,000 USD (240,000,000 COP) per year.\n"
).strip()  # the generator strips every draft, so the test drafts are stripped too
OPS_BAD = OPS_GOOD.replace("takes 10 business days", "takes 5 business days")
MKT_GOOD = (
    "## Brand and Commercial Terms\n"
    "- Brasaland offers Sunset Bay Resorts a co-branded concession built on consistent "
    "quality, warm experience and speed of service.\n"
    "- The contract value is $60,000 USD (240,000,000 COP) per year.\n"
    "- This offer is valid for 30 days from issuance.\n"
).strip()


class ScriptedModel:
    """Plays every agent. `drafts` maps a department title to the drafts its
    generator returns, one per call (the last one repeats)."""

    def __init__(self, drafts=None, fail_generator_on_call=None, wait_for_both_generators=False):
        self.drafts = {
            "Operations and Delivery": [OPS_GOOD],
            "Brand and Commercial Terms": [MKT_GOOD],
        }
        self.drafts.update(drafts or {})
        self.generator_prompts = []  # (title, prompt, system)
        self.fail_generator_on_call = fail_generator_on_call
        self.generator_calls = 0
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(2, timeout=5) if wait_for_both_generators else None
        self.waited = set()

    def __call__(self, prompt, *, system=None):
        if "drafting one section" in system:
            title = re.search(r"belongs to the (.+?) department", system).group(1)
            with self.lock:
                self.generator_calls += 1
                call_number = self.generator_calls
                self.generator_prompts.append((title, prompt, system))
                queue = self.drafts[title]
                draft = queue.pop(0) if len(queue) > 1 else queue[0]
                first_time = title not in self.waited
                self.waited.add(title)
            if self.barrier and first_time:
                self.barrier.wait()
            if self.fail_generator_on_call == call_number:
                raise RuntimeError("model is down")
            return draft
        if "relevance checker" in system:
            return json.dumps({"missing": []})
        if "competitor checker" in system:
            return json.dumps({"competitors": []})
        raise AssertionError("unexpected agent")


def use(monkeypatch, model):
    monkeypatch.setattr(llm, "call_generation_llm", model)
    return model


def ops_loop(**options):
    return loop.run_section_loop("operaciones", METADATA, OPS_ASPECTS, [], **options)


# --- the loop for one department -------------------------------------------------

def test_section_that_passes_first_time_needs_one_draft(monkeypatch):
    model = use(monkeypatch, ScriptedModel())
    section = ops_loop()
    assert section["status"] == "passed"
    assert section["iterations"] == 1
    assert section["draft_content"] == OPS_GOOD
    assert section["evaluation_result"]["overall_pass"] is True
    assert section["error"] is None
    assert model.generator_calls == 1


def test_failed_evaluation_sends_concrete_feedback_back_to_the_same_generator(monkeypatch):
    # The ticket's "evaluation fails" case, end to end: the first draft breaks
    # the setup-time rule, the second one is fixed after seeing the feedback.
    model = use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD, OPS_GOOD]}))
    section = ops_loop()

    assert section["status"] == "passed"
    assert section["iterations"] == 2
    assert section["draft_content"] == OPS_GOOD
    assert [h["overall_pass"] for h in section["history"]] == [False, True]
    assert section["history"][0]["rule_ids"] == ["NO-INVENTED-NUMBERS", "SETUP-MIN-10-DAYS"]

    first_title, first_prompt, _ = model.generator_prompts[0]
    second_title, second_prompt, _ = model.generator_prompts[1]
    assert first_title == second_title == "Operations and Delivery"
    assert "previous draft" not in first_prompt
    assert OPS_BAD in second_prompt                      # it sees its own last draft...
    assert "SETUP-MIN-10-DAYS" in second_prompt          # ...and the exact rule that broke
    assert "takes 5 business days" in second_prompt      # ...and the sentence that broke it


def test_iteration_limit_stops_the_loop_and_keeps_the_last_draft_and_result(monkeypatch):
    model = use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD]}))
    section = ops_loop()

    assert model.generator_calls == settings.ITERATION_LIMIT   # it really stops
    assert section["iterations"] == settings.ITERATION_LIMIT
    assert section["status"] == "needs_human_review"
    assert section["draft_content"] == OPS_BAD                 # the draft is kept, not dropped
    assert section["evaluation_result"]["overall_pass"] is False
    assert "SETUP-MIN-10-DAYS" in section["evaluation_result"]["compliance"]["rule_ids"]
    assert len(section["history"]) == settings.ITERATION_LIMIT


def test_the_limit_can_be_set_for_one_call(monkeypatch):
    model = use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD]}))
    section = ops_loop(limit=2)
    assert model.generator_calls == 2 and section["iterations"] == 2


def test_model_failure_in_a_later_draft_keeps_the_last_evaluated_draft(monkeypatch):
    use(monkeypatch, ScriptedModel(
        drafts={"Operations and Delivery": [OPS_BAD, OPS_GOOD]}, fail_generator_on_call=2))
    section = ops_loop()
    assert section["status"] == "needs_human_review"
    assert section["draft_content"] == OPS_BAD
    assert section["evaluation_result"]["overall_pass"] is False   # the pair belongs together
    assert "model is down" in section["error"]
    assert section["iterations"] == 2


def test_model_failure_on_the_very_first_draft_leaves_an_empty_section_with_the_error(monkeypatch):
    use(monkeypatch, ScriptedModel(fail_generator_on_call=1))
    section = ops_loop()
    assert section["status"] == "needs_human_review"
    assert section["draft_content"] == "" and section["evaluation_result"] is None
    assert "model is down" in section["error"]


def test_progress_is_reported_in_order(monkeypatch):
    use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD, OPS_GOOD]}))
    events = []
    ops_loop(on_progress=lambda dept, stage, n: events.append((dept, stage, n)))
    assert events == [
        ("operaciones", "drafting", 1), ("operaciones", "evaluating", 1),
        ("operaciones", "drafting", 2), ("operaciones", "evaluating", 2),
        ("operaciones", "finished", 2),
    ]


def test_a_failing_progress_callback_never_stops_the_draft(monkeypatch):
    use(monkeypatch, ScriptedModel())

    def broken(dept, stage, n):
        raise RuntimeError("database is down")

    section = ops_loop(on_progress=broken)
    assert section["status"] == "passed"


# --- the graph: all departments -------------------------------------------------

INPUTS = {
    "marketing": {"key_aspects": MKT_ASPECTS, "open_questions": []},
    "operaciones": {"key_aspects": OPS_ASPECTS, "open_questions": []},
}


def test_every_department_gets_a_finished_section_and_the_ticket_rests_at_under_evaluation(monkeypatch):
    use(monkeypatch, ScriptedModel())
    state = graph.run_response(7, METADATA, INPUTS)
    assert state["status"] == "under_evaluation"
    assert state["ticket_id"] == 7 and state["error"] is None
    assert set(state["results"]) == {"marketing", "operaciones"}
    assert all(s["status"] == "passed" for s in state["results"].values())
    assert state["average_iterations"] == 1.0


def test_one_section_out_of_drafts_makes_the_ticket_needs_human_review_but_nothing_is_dropped(monkeypatch):
    use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD]}))
    state = graph.run_response(7, METADATA, INPUTS)
    assert state["status"] == "needs_human_review"
    assert set(state["results"]) == {"marketing", "operaciones"}
    assert state["results"]["marketing"]["status"] == "passed"
    assert state["results"]["operaciones"]["status"] == "needs_human_review"
    assert state["results"]["operaciones"]["draft_content"] == OPS_BAD
    assert state["average_iterations"] == (1 + settings.ITERATION_LIMIT) / 2


def test_each_generator_only_sees_its_own_departments_aspects(monkeypatch):
    model = use(monkeypatch, ScriptedModel())
    graph.run_response(7, METADATA, INPUTS)
    prompts = {title: prompt for title, prompt, _ in model.generator_prompts}
    assert "OPS-ONLY" in prompts["Operations and Delivery"]
    assert "MKT-ONLY" not in prompts["Operations and Delivery"]
    assert "MKT-ONLY" in prompts["Brand and Commercial Terms"]
    assert "OPS-ONLY" not in prompts["Brand and Commercial Terms"]


def test_departments_really_run_at_the_same_time(monkeypatch):
    # Each generator waits for the other one's first call. One department after
    # the other would time out, so this only passes if they run in parallel.
    use(monkeypatch, ScriptedModel(wait_for_both_generators=True))
    state = graph.run_response(7, METADATA, INPUTS)
    assert state["status"] == "under_evaluation"


def test_only_the_departments_in_the_handoff_are_run(monkeypatch):
    model = use(monkeypatch, ScriptedModel())
    state = graph.run_response(7, METADATA, {"operaciones": INPUTS["operaciones"]})
    assert list(state["results"]) == ["operaciones"]
    assert {title for title, _, _ in model.generator_prompts} == {"Operations and Delivery"}


def test_progress_is_reported_for_every_department(monkeypatch):
    use(monkeypatch, ScriptedModel())
    events = []
    lock = threading.Lock()

    def record(dept, stage, n):
        with lock:
            events.append((dept, stage, n))

    graph.run_response(7, METADATA, INPUTS, on_progress=record)
    assert {(d, s) for d, s, _ in events if s == "finished"} == {("marketing", "finished"), ("operaciones", "finished")}


def test_a_handoff_with_no_departments_or_an_unknown_one_is_refused():
    with pytest.raises(ValueError):
        graph.run_response(7, METADATA, {})
    with pytest.raises(ValueError):
        graph.run_response(7, METADATA, {"finance": {"key_aspects": [], "open_questions": []}})


def test_a_crash_inside_the_run_is_reported_as_failed_not_raised(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(graph, "run_section_loop", boom)
    state = graph.run_response(7, METADATA, INPUTS)
    assert state["status"] == "failed"
    assert "graph exploded" in state["error"]


def test_final_status_rules():
    passed = {"status": "passed", "iterations": 1}
    review = {"status": "needs_human_review", "iterations": 3}
    assert graph.final_status({"a": passed, "b": passed}) == "under_evaluation"
    assert graph.final_status({"a": passed, "b": review}) == "needs_human_review"
    assert graph.final_status({}) == "failed"


# --- Part 3: start from an existing draft and a person's feedback ----------------

def test_the_loop_can_start_from_an_existing_draft_and_a_persons_feedback(monkeypatch):
    model = use(monkeypatch, ScriptedModel())
    section = ops_loop(previous_draft="THE DRAFT THE APPROVER SAW", feedback="REVIEW by Felipe: add the staffing plan")
    assert section["status"] == "passed" and section["iterations"] == 1
    title, prompt, _ = model.generator_prompts[0]
    assert "THE DRAFT THE APPROVER SAW" in prompt            # the first draft is already a revision
    assert "REVIEW by Felipe: add the staffing plan" in prompt


def test_a_normal_first_run_still_starts_from_a_blank_page(monkeypatch):
    model = use(monkeypatch, ScriptedModel())
    ops_loop()
    assert "previous draft" not in model.generator_prompts[0][1]
