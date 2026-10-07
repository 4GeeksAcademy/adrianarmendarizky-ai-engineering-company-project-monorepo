"""
tests/pipelines/test_rfp_trace.py -- the trace of Part 1 and Part 2
(data/pipelines/rfp_trace.py): every node the intake graph and the response
graph run leaves one event, and each draft round of a department's loop does
too. Nothing is stored anywhere: the tests collect the events in a list.

The two graphs run for real, with the same fake models as their own tests
(test_rfp_graph.py for Part 1, test_rfp_response_loop.py for Part 2).
"""

import json
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

import rfp_trace  # noqa: E402
from rfp_intake import graph as intake_graph  # noqa: E402
from rfp_response import graph as response_graph  # noqa: E402
from test_rfp_graph import setup as intake_setup  # noqa: E402  (the fake model of the intake tests)
from test_rfp_response_loop import (  # noqa: E402  (the fake model of the response tests)
    INPUTS, METADATA, OPS_BAD, OPS_GOOD, ScriptedModel, use,
)


class Sink:
    """Collects events. Thread-safe, because the departments run in parallel."""

    def __init__(self):
        self.events = []
        self._lock = threading.Lock()

    def __call__(self, event):
        with self._lock:
            self.events.append(event)

    def agents(self):
        return [e["agent"] for e in self.events]


# --- Part 2: the response graph --------------------------------------------------------------

def test_every_department_and_the_finish_step_leave_an_event(monkeypatch):
    use(monkeypatch, ScriptedModel())
    sink = Sink()
    with rfp_trace.tracing(7, 2, "response", sink):
        state = response_graph.run_response(7, METADATA, INPUTS)

    assert state["status"] == "under_evaluation"
    assert sorted(sink.agents()) == ["response:finish", "response:section", "response:section"]
    assert sink.agents()[-1] == "response:finish"                       # the sections finished first
    sections = [e for e in sink.events if e["agent"] == "response:section"]
    assert sorted(e["subject"] for e in sections) == ["marketing", "operaciones"]
    for event in sink.events:
        assert event["ticket_id"] == 7 and event["part"] == 2
        assert event["event_type"] == "node_finished" and event["timestamp"] and event["actor"] is None
        json.dumps(event)                                                # storable as it is


def test_what_a_department_was_given_and_what_it_returned_are_in_its_event(monkeypatch):
    use(monkeypatch, ScriptedModel())
    sink = Sink()
    with rfp_trace.tracing(7, 2, "response", sink):
        response_graph.run_response(7, METADATA, INPUTS)
    event = next(e for e in sink.events if e["agent"] == "response:section" and e["subject"] == "operaciones")
    assert event["input"]["department_id"] == "operaciones"
    assert "OPS-ONLY" in json.dumps(event["input"])                      # its own facts went in...
    assert event["output"]["results"]["operaciones"]["status"] == "passed"   # ...and its result came out


def test_each_draft_round_is_traced_in_order(monkeypatch):
    use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD, OPS_GOOD]}))
    sink = Sink()
    with rfp_trace.tracing(7, 2, "response", sink) as tracer:
        response_graph.run_response(7, METADATA, INPUTS, on_progress=tracer.progress)

    rounds = [(e["agent"], e["input"]["draft"]) for e in sink.events
              if e["event_type"] == "progress" and e["subject"] == "operaciones"]
    assert rounds == [
        ("response:drafting", 1), ("response:evaluating", 1),
        ("response:drafting", 2), ("response:evaluating", 2),
        ("response:finished", 2),
    ]


def test_a_crashing_node_is_traced_as_failed(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(response_graph, "run_section_loop", boom)
    sink = Sink()
    with rfp_trace.tracing(7, 2, "response", sink):
        state = response_graph.run_response(7, METADATA, INPUTS)
    assert state["status"] == "failed"
    failed = [e for e in sink.events if e["event_type"] == "node_failed"]
    assert failed and failed[0]["agent"] == "response:section"
    assert "graph exploded" in failed[0]["output"]["error"]


# --- Part 1: the intake graph ----------------------------------------------------------------

def test_the_intake_graph_traces_every_step_in_order(monkeypatch):
    intake_setup(monkeypatch, departments=("marketing", "operaciones"))
    sink = Sink()
    with rfp_trace.tracing(7, 1, "intake", sink):
        state = intake_graph.run_intake("fake.pdf", ticket_id=7)

    assert state["status"] == "intake_complete"
    agents = sink.agents()
    assert agents[:3] == ["intake:convert", "intake:classify", "intake:orchestrate"]
    assert sorted(agents[3:5]) == ["intake:worker", "intake:worker"]
    assert agents[5] == "intake:synthesize" and len(agents) == 6
    workers = [e for e in sink.events if e["agent"] == "intake:worker"]
    assert sorted(e["subject"] for e in workers) == ["marketing", "operaciones"]
    for event in sink.events:
        assert event["ticket_id"] == 7 and event["part"] == 1 and event["timestamp"]
        json.dumps(event)


def test_a_discarded_document_is_traced_only_as_far_as_the_classifier(monkeypatch):
    intake_setup(monkeypatch, is_rfp=False)
    sink = Sink()
    with rfp_trace.tracing(7, 1, "intake", sink):
        state = intake_graph.run_intake("fake.pdf", ticket_id=7)
    assert state["status"] == "discarded"
    assert sink.agents() == ["intake:convert", "intake:classify"]


# --- switching it on and off ---------------------------------------------------------------------

def test_nothing_is_traced_unless_it_is_switched_on(monkeypatch):
    use(monkeypatch, ScriptedModel())
    assert rfp_trace.active() is None and rfp_trace.config() is None
    sink = Sink()
    response_graph.run_response(7, METADATA, INPUTS)                      # no `with` block
    assert sink.events == []


def test_the_tracer_is_only_active_inside_its_block():
    sink = Sink()
    with rfp_trace.tracing(1, 1, "intake", sink) as outer:
        assert rfp_trace.active() is outer
        with rfp_trace.tracing(2, 2, "response", sink) as inner:
            assert rfp_trace.active() is inner
        assert rfp_trace.active() is outer
    assert rfp_trace.active() is None


def test_tracing_changes_nothing_about_the_result(monkeypatch):
    use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD, OPS_GOOD]}))
    plain = response_graph.run_response(7, METADATA, INPUTS)
    use(monkeypatch, ScriptedModel(drafts={"Operations and Delivery": [OPS_BAD, OPS_GOOD]}))
    with rfp_trace.tracing(7, 2, "response", Sink()):
        traced = response_graph.run_response(7, METADATA, INPUTS)
    for result in (plain, traced):
        result["results"] = {d: {k: s[k] for k in ("status", "iterations", "draft_content")} for d, s in result["results"].items()}
    assert plain == traced


def test_a_sink_that_fails_never_stops_the_pipeline(monkeypatch):
    use(monkeypatch, ScriptedModel())

    def broken(event):
        raise RuntimeError("database is down")

    with rfp_trace.tracing(7, 2, "response", broken) as tracer:
        state = response_graph.run_response(7, METADATA, INPUTS, on_progress=tracer.progress)
    assert state["status"] == "under_evaluation"


# --- keeping events short and storable --------------------------------------------------------------

def test_events_are_cut_down_to_something_short_and_storable():
    cleaned = rfp_trace.clean({
        "markdown": "word " * 500,
        "callback": lambda: None,
        "numbers": list(range(100)),
        "deep": {"a": {"b": {"c": {"d": {"e": 1}}}}},
        "tags": {"x", "y"},
        "fine": [1, 2.5, True, None, "text"],
    })
    json.dumps(cleaned)
    assert len(cleaned["markdown"]) < 400 and cleaned["markdown"].endswith("characters)")
    assert cleaned["callback"] == "<function>"
    assert len(cleaned["numbers"]) == 13 and cleaned["numbers"][-1] == "(+88 more)"
    assert cleaned["deep"]["a"]["b"]["c"] == "<dict>"
    assert sorted(cleaned["tags"]) == ["x", "y"]
    assert cleaned["fine"] == [1, 2.5, True, None, "text"]
