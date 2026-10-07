"""
rfp_trace.py -- a trace of every node the Part 1 and Part 2 graphs run
(Milestone 9, Part 3: "log the agent, input, output and timestamp for every node
execution").

Part 3's own graphs (data/pipelines/rfp_approval/) already log their steps. This
does the same for the intake graph (Part 1) and the response graph (Part 2), so
one ticket has ONE trace from the PDF to the final document.

How it works, in short:

  - NodeTrace is an observer LangGraph calls whenever one of the graph's nodes
    starts and finishes. It never touches the node code, and it never changes
    what a node returns.
  - tracing(...) switches it on for the duration of a `with` block. The graph
    functions (run_intake, run_response) look for it and pass it to the graph.
    With no `with` block around them, nothing is traced and nothing else changes.
  - Every event is a plain dict, the same shape as Part 3's events:
        ticket_id, part, agent, event_type, subject, input, output, actor, timestamp
    and goes to a sink (in the API, the rfp_events table). A sink that fails
    never stops the pipeline.
  - progress(...) adds one event per drafting / evaluating / finished step of
    each department's loop, so each draft round shows up in order.
"""

import contextlib
import contextvars
import threading
from datetime import datetime, timezone

from langchain_core.callbacks import BaseCallbackHandler

MAX_TEXT = 300     # longer text is cut, so the trace stays readable
MAX_ITEMS = 12     # longer lists / dicts are cut
MAX_DEPTH = 4      # deeper nesting is replaced by a short description


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def clean(value, depth: int = 0):
    """A short, JSON-safe copy of anything a node was given or returned.
    Long text is cut, big containers are shortened, and things that cannot be
    stored (functions, objects) are replaced by their type name."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > MAX_TEXT:
            return value[:MAX_TEXT] + f"... (+{len(value) - MAX_TEXT} characters)"
        return value
    if depth >= MAX_DEPTH:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        items = list(value.items())
        cut = {str(key): clean(item, depth + 1) for key, item in items[:MAX_ITEMS]}
        if len(items) > MAX_ITEMS:
            cut["..."] = f"(+{len(items) - MAX_ITEMS} more)"
        return cut
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        cut = [clean(item, depth + 1) for item in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            cut.append(f"(+{len(items) - MAX_ITEMS} more)")
        return cut
    return f"<{type(value).__name__}>"


class NodeTrace(BaseCallbackHandler):
    """Records one event per graph node run. part is 1 (intake) or 2 (response);
    prefix names the graph in the agent name ("intake:classify")."""

    def __init__(self, ticket_id, part: int, prefix: str, sink):
        self.ticket_id = ticket_id
        self.part = part
        self.prefix = prefix
        self.sink = sink
        self._runs: dict = {}
        self._lock = threading.Lock()

    # --- sending -----------------------------------------------------------

    def _send(self, event: dict) -> None:
        try:
            self.sink(event)
        except Exception as error:  # a trace that cannot be stored never stops the pipeline
            print(f"RFP trace: could not store an event ({error})")

    def _event(self, agent: str, event_type: str, subject, input_data, output_data) -> dict:
        return {
            "ticket_id": self.ticket_id, "part": self.part, "agent": agent, "event_type": event_type,
            "subject": subject, "input": input_data, "output": output_data,
            "actor": None, "timestamp": now_iso(),
        }

    # --- what LangGraph calls ---------------------------------------------------

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        node = (metadata or {}).get("langgraph_node")
        # Only the node itself: not the routing functions around it, and not LangGraph's own
        # internal steps ("__start__" and the like), which would only be noise in the trace.
        if node and not node.startswith("__") and kwargs.get("name") == node:
            with self._lock:
                self._runs[run_id] = (node, clean(inputs), inputs.get("department_id") if isinstance(inputs, dict) else None)

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        with self._lock:
            started = self._runs.pop(run_id, None)
        if started:
            node, input_data, subject = started
            self._send(self._event(f"{self.prefix}:{node}", "node_finished", subject, input_data, clean(outputs)))

    def on_chain_error(self, error, *, run_id, **kwargs):
        with self._lock:
            started = self._runs.pop(run_id, None)
        if started:
            node, input_data, subject = started
            output = {"error": f"{type(error).__name__}: {error}"}
            self._send(self._event(f"{self.prefix}:{node}", "node_failed", subject, input_data, output))

    # --- the loop inside a department (Part 2) -----------------------------------

    def progress(self, department_id: str, stage: str, iteration: int) -> None:
        """One event per drafting / evaluating / finished step of a department's loop."""
        self._send(self._event(f"{self.prefix}:{stage}", "progress", department_id, {"draft": iteration}, {}))


# ---------------------------------------------------------------------------
# Switching it on
# ---------------------------------------------------------------------------

_active: contextvars.ContextVar = contextvars.ContextVar("rfp_active_trace", default=None)


@contextlib.contextmanager
def tracing(ticket_id, part: int, prefix: str, sink):
    """Trace the graph run started inside this `with` block:

        with rfp_trace.tracing(ticket_id, 1, "intake", store_event) as tracer:
            state = run_intake(pdf, ticket_id=ticket_id)
    """
    tracer = NodeTrace(ticket_id, part, prefix, sink)
    token = _active.set(tracer)
    try:
        yield tracer
    finally:
        _active.reset(token)


def active():
    """The tracer switched on by the nearest `with tracing(...)`, or None."""
    return _active.get()


def config():
    """The extra setting run_intake / run_response pass to the graph: the tracer, or None."""
    tracer = _active.get()
    return {"callbacks": [tracer]} if tracer is not None else None
