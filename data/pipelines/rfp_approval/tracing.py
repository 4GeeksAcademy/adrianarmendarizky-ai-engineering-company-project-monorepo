"""
tracing.py -- one trace event per node execution (Milestone 9, Part 3).

Every event says WHICH agent ran, with what INPUT, what it OUTPUT, and WHEN
(plus who, for human actions). Events are kept in the graph's own state
("trace") and, when a sink is given, also handed to the sink so the API can
store them in the rfp_events table.

Important for graphs that pause: LangGraph runs a paused node again from its
first line when it is resumed. So an event is only written AFTER a node
finishes, never before an interrupt.
"""

from datetime import datetime, timezone

MAX_TEXT = 300


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _short(value):
    """Keep events readable: cut long text, and look inside small containers."""
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + f"... (+{len(value) - MAX_TEXT} characters)"
    if isinstance(value, dict):
        return {key: _short(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_short(item) for item in value]
    return value


def make_event(agent: str, subject, input_data: dict, output_data: dict, actor=None,
               event_type: str = "node_finished") -> dict:
    return {
        "part": 3,
        "agent": agent,
        "event_type": event_type,
        "subject": subject,
        "input": _short(input_data),
        "output": _short(output_data),
        "actor": actor,
        "timestamp": now_iso(),
    }


def send(sink, event: dict) -> None:
    """Hand an event to the sink. A sink that fails never stops the workflow."""
    if sink is None:
        return
    try:
        sink(event)
    except Exception as error:
        print(f"RFP approval: could not store a trace event ({error})")


def traced(agent: str, sink=None, input_keys=()):
    """Wrap a node so that, once it finishes, it adds its own trace event."""
    def decorator(node):
        def wrapped(state):
            update = node(state)
            event = make_event(
                agent, state.get("subject"),
                {key: state.get(key) for key in input_keys if key in state},
                {key: value for key, value in update.items() if key != "trace"},
                actor=update.get("acted_by") or state.get("acted_by"),
            )
            update["trace"] = [event]
            send(sink, event)
            return update
        wrapped.__name__ = node.__name__
        return wrapped
    return decorator
