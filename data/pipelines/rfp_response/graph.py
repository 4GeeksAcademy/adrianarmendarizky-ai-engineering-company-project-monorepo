"""
graph.py -- the RFP response graph (Milestone 9, Part 2).

Its own graph, separate from Part 1's intake graph. It starts from Part 1's
handoff and never reads the PDF:

    ticket_id + metadata + each department's key_aspects / open_questions

Shape:

    START -> [one "section" per department, in parallel] -> finish -> END

Each "section" runs that department's whole generate / evaluate / revise loop
(loop.py). A slow department never blocks the others. The departments share
nothing while they run; each returns its own result, and the results are
merged by key at the end.

Ticket status for the whole run (CONTEXT-brasaland.md section 2.3):
  needs_human_review  at least one section ran out of drafts (or broke down)
  under_evaluation    every section passed; Part 3 picks up from here
  failed              the graph itself crashed (our own addition, as in Part 1)
"""

import operator
from functools import lru_cache
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from rfp_intake.state import DEPARTMENT_IDS

from . import settings
from .loop import SECTION_PASSED, run_section_loop

STATUS_FAILED = "failed"


class RfpResponseState(TypedDict, total=False):
    # Comes in with the handoff from Part 1
    ticket_id: int
    metadata: dict
    inputs: dict  # department_id -> {"key_aspects": [...], "open_questions": [...]}
    progress: Any  # optional on_progress callback

    # Each section adds its own department. operator.or_ merges the dicts.
    results: Annotated[dict, operator.or_]

    # Set by the finish step
    status: str
    average_iterations: float


def fan_out(state: dict):
    """Start one section per department, always in the same order."""
    return [
        Send("section", {
            "department_id": department_id,
            "metadata": state["metadata"],
            # Only this department's own facts travel with it.
            "key_aspects": state["inputs"][department_id]["key_aspects"],
            "open_questions": state["inputs"][department_id]["open_questions"],
            "progress": state.get("progress"),
        })
        for department_id in DEPARTMENT_IDS
        if department_id in state["inputs"]
    ]


def section_node(payload: dict) -> dict:
    department_id = payload["department_id"]
    result = run_section_loop(
        department_id, payload["metadata"], payload["key_aspects"], payload["open_questions"],
        on_progress=payload.get("progress"),
    )
    return {"results": {department_id: result}}


def final_status(results: dict) -> str:
    if not results:
        return STATUS_FAILED
    if any(section["status"] != SECTION_PASSED for section in results.values()):
        return settings.STATUS_NEEDS_HUMAN_REVIEW
    return settings.STATUS_UNDER_EVALUATION


def finish_node(state: dict) -> dict:
    results = state.get("results", {})
    average = (
        sum(section["iterations"] for section in results.values()) / len(results)
        if results else 0.0
    )
    return {"status": final_status(results), "average_iterations": round(average, 2)}


def build_graph():
    builder = StateGraph(RfpResponseState)
    builder.add_node("section", section_node)
    builder.add_node("finish", finish_node)
    builder.add_conditional_edges(START, fan_out)
    builder.add_edge("section", "finish")  # waits for every section
    builder.add_edge("finish", END)
    return builder.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def run_response(ticket_id: int, metadata: dict, inputs: dict, on_progress=None) -> dict:
    """Run the whole response for one ticket and return the final state:
    results (one finished section per department), status, average_iterations.

    Raises ValueError for a handoff that makes no sense (no departments, or a
    department that isn't one of the four). Anything that crashes INSIDE the
    run is reported as status "failed" with the error, never raised.
    """
    if not inputs:
        raise ValueError("The handoff has no departments.")
    unknown = sorted(set(inputs) - set(DEPARTMENT_IDS))
    if unknown:
        raise ValueError(f"Unknown department(s) in the handoff: {unknown}")

    start = {"ticket_id": ticket_id, "metadata": metadata, "inputs": inputs, "progress": on_progress}
    try:
        state = get_graph().invoke(start)
    except Exception as error:  # last safety net: the graph itself blew up
        return {
            "ticket_id": ticket_id, "results": {}, "status": STATUS_FAILED,
            "average_iterations": 0.0,
            "error": f"response run crashed: {type(error).__name__}: {error}",
        }
    return {
        "ticket_id": ticket_id,
        "results": state.get("results", {}),
        "status": state["status"],
        "average_iterations": state["average_iterations"],
        "error": None,
    }
