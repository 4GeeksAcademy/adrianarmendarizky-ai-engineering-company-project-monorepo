"""
graph.py -- the RFP intake graph (Milestone 9, Part 1).

This is its own graph. It shares nothing with the support agent's graph in
services/api/agent/graph.py.

Shape:

    START -> convert -> classify -> [is it an RFP?]
                                     no  -> END   (ticket becomes "discarded")
                                     yes -> orchestrate
                                            -> worker (one per department, in parallel)
                                            -> synthesize -> END

If any step crashes, its error is saved in state["error"] and the graph
stops. run_intake() then reports the status "failed", so a ticket is never
left stuck on "analyzing".

Routers (services/api/routes/) only call run_intake(). They do not own any
of this logic.
"""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import rfp_trace  # data/pipelines/rfp_trace.py: an optional trace of every node (the API switches it on)

from .classifier import classify_node
from .convert import compute_readability, detect_language, pdf_to_markdown
from .orchestrator import orchestrate_node
from .state import RfpIntakeState
from .synthesizer import synthesize_node
from .workers import WORKERS

# Ticket statuses set at the end (same strings as rfp_models.py).
STATUS_INTAKE_COMPLETE = "intake_complete"
STATUS_DISCARDED = "discarded"
STATUS_FAILED = "failed"


def safe(step_name, step):
    """Wrap a step so a crash becomes state["error"] instead of an exception.
    If an earlier step already failed, do nothing."""
    def wrapped(state):
        if state.get("error"):
            return {}
        try:
            return step(state)
        except Exception as error:
            return {"error": f"{step_name} step failed: {type(error).__name__}: {error}"}
    return wrapped


def convert_node(state: dict) -> dict:
    markdown = pdf_to_markdown(state["pdf_path"])
    if not markdown.strip():
        raise ValueError("No text could be read from the PDF (it may be a scanned image).")
    return {
        "markdown": markdown,
        "language": detect_language(markdown),
        "readability": compute_readability(markdown),
    }


def worker_node(payload: dict) -> dict:
    """Runs ONE department's worker. It receives only the shared metadata
    and that department's extract, never the whole state."""
    department_id = payload["department_id"]
    try:
        section = WORKERS[department_id](payload["metadata"], payload["extract"])
    except Exception as error:
        return {"error": f"worker '{department_id}' failed: {type(error).__name__}: {error}"}
    return {"sections": {department_id: section}}


# --- routing -----------------------------------------------------------

def after_convert(state: dict):
    return END if state.get("error") else "classify"


def after_classify(state: dict):
    if state.get("error") or not state.get("is_rfp"):
        return END  # discarded (or crashed): stop here, no workers, no more model calls
    return "orchestrate"


def fan_out(state: dict):
    """After the orchestrator: start one worker per department that applies."""
    if state.get("error"):
        return END
    return [
        Send("worker", {
            "department_id": department_id,
            "metadata": state["metadata"],
            "extract": state["assignments"][department_id]["extract"],
        })
        for department_id in state["departments_needed"]
    ]


# --- building and running ------------------------------------------------

def build_graph():
    builder = StateGraph(RfpIntakeState)
    builder.add_node("convert", safe("convert", convert_node))
    builder.add_node("classify", safe("classify", classify_node))
    builder.add_node("orchestrate", safe("orchestrate", orchestrate_node))
    builder.add_node("worker", worker_node)
    builder.add_node("synthesize", safe("synthesize", synthesize_node))

    builder.add_edge(START, "convert")
    builder.add_conditional_edges("convert", after_convert)
    builder.add_conditional_edges("classify", after_classify)
    builder.add_conditional_edges("orchestrate", fan_out)
    builder.add_edge("worker", "synthesize")  # waits for every worker
    builder.add_edge("synthesize", END)
    return builder.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def final_status(state: dict) -> str:
    if state.get("error"):
        return STATUS_FAILED
    if state.get("is_rfp") is False:
        return STATUS_DISCARDED
    if state.get("sales_summary"):
        return STATUS_INTAKE_COMPLETE
    return STATUS_FAILED  # finished without a summary: never report success


def run_intake(pdf_path, ticket_id=None) -> dict:
    """Run the whole intake for one PDF and return the final state, with a
    "status" key added. Never raises."""
    start = {"pdf_path": str(pdf_path)}
    if ticket_id is not None:
        start["ticket_id"] = ticket_id
    try:
        state = get_graph().invoke(start, config=rfp_trace.config())
    except Exception as error:  # last safety net: the graph itself blew up
        state = {**start, "error": f"pipeline crashed: {type(error).__name__}: {error}"}
    state["status"] = final_status(state)
    return state
