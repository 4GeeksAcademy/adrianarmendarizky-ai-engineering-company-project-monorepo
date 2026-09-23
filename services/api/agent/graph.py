"""
services/api/agent/graph.py -- Part 1 of 2 (LangGraph migration): builds
and compiles the agent graph, and exposes get_trace() for inspecting a
run after the fact.

Graph shape:

    START -> receive_question -> retrieve --[context found]--> generate -> END
                                          \\--[context empty]--> no_info -> END

build_graph() returns the uncompiled StateGraph; `graph` (module-level,
built once at import time) is the compiled, checkpointed, ready-to-invoke
version everything else should import and use.

Checkpointing: a real, file-backed SqliteSaver, not the in-memory kind --
every state transition is written to services/api/agent_checkpoints.db,
so get_state_history() (and therefore get_trace() below) stays queryable
after the process exits, not just for the lifetime of one run. That file
is a runtime artifact, not source -- it's gitignored, not committed.

compile() (called once, at the bottom of this module) is what actually
validates the graph -- an unconnected node, a route_after_retrieve
returning a value with no matching path_map entry, etc. all raise here,
at import time, with a clear message -- never as a confusing failure
mid-request.
"""

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from .nodes import (
    generate_node,
    no_info_node,
    receive_question_node,
    retrieve_node,
    route_after_retrieve,
)
from .state import AgentState

CHECKPOINT_DB = Path(__file__).resolve().parent.parent / "agent_checkpoints.db"


def build_graph() -> StateGraph:
    """Assembles the uncompiled graph. Split out from the compiled
    `graph` singleton below purely so a test can build (and separately
    compile, with its own throwaway checkpointer) a fresh instance
    without touching the real checkpoint database."""
    builder = StateGraph(AgentState)
    builder.add_node("receive_question", receive_question_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.add_node("no_info", no_info_node)

    builder.add_edge(START, "receive_question")
    builder.add_edge("receive_question", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "no_info": "no_info"},
    )
    builder.add_edge("generate", END)
    builder.add_edge("no_info", END)
    return builder


# Opened once, for the lifetime of the process -- not per-request. The
# context manager is entered manually (rather than via `with`) because
# there's no natural place to exit it: this module is imported once at
# app startup and the connection should simply live as long as the app
# does, the same way data/pipelines/rag.py's own Qdrant client is a
# single long-lived module-level object.
_checkpointer_cm = SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
_checkpointer = _checkpointer_cm.__enter__()

graph: CompiledStateGraph = build_graph().compile(checkpointer=_checkpointer)


def get_trace(config: dict) -> list[dict]:
    """Returns the ordered list of node executions for one run (by its
    thread_id, inside `config`):
        [{"node": "retrieve", "output": {"context": [...]}}, ...]
    This is the queryable trace the ticket asks for -- which nodes ran,
    in what order, and what each one actually produced -- built from
    get_state_history(), which reads back from the SQLite checkpoint
    file, not from anything held only in memory during the run."""
    history = list(graph.get_state_history(config))
    history.reverse()  # oldest (the initial input) first
    trace = []
    for prev, curr in zip(history, history[1:]):
        node_name = prev.next[0] if prev.next else "?"
        changed = {k: v for k, v in curr.values.items() if prev.values.get(k) != v}
        trace.append({"node": node_name, "output": changed})
    return trace
