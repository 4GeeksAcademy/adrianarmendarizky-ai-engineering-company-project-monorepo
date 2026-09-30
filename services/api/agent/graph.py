"""
services/api/agent/graph.py -- Part 2 of 2 (external tools): builds and
compiles the agent graph.

Graph shape (extended from Part 1):

    START -> receive_question -> check_pending -> load_memory -> [route_question] -> any subset of:
                                       ticket_tool
                                       inventory_tool
                                       retrieve
                                  (chosen in parallel when more than one
                                   applies -- this is the "RAG, a tool,
                                   or both" the ticket asks for)
             all chosen branches -> generate -> self_evaluate -> END

check_pending, load_memory and self_evaluate are the agent-memory steps
(Milestone 8, Part 1; see memory_nodes.py). When the message only answers a
memory proposal, check_pending jumps straight to self_evaluate.

route_question (in nodes.py) is the one real routing decision, based on
the question's content: a ticket ID pattern routes to ticket_tool, a
stock/inventory mention routes to inventory_tool, and either a policy
keyword or the absence of any tool signal routes to retrieve (the RAG).
More than one can fire at once.

Every chosen branch feeds into the same generate node rather than each
having its own conditional exit -- see nodes.py's module docstring for
why: a conditional edge can't reliably see what a sibling parallel
branch just wrote, so "did we find anything, anywhere?" has to be
decided in the one node all of them funnel into, not before it.

build_graph()/graph/get_trace() unchanged in shape and purpose from
Part 1 -- same SQLite checkpointer, same trace mechanism, now just
covering more node types.
"""

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from .memory_nodes import (
    check_pending_node,
    load_memory_node,
    route_after_decision,
    self_evaluate_node,
)
from .nodes import (
    generate_node,
    inventory_tool_node,
    receive_question_node,
    retrieve_node,
    route_question,
    ticket_tool_node,
)
from .state import AgentState

CHECKPOINT_DB = Path(__file__).resolve().parent.parent / "agent_checkpoints.db"


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("receive_question", receive_question_node)
    builder.add_node("ticket_tool", ticket_tool_node)
    builder.add_node("inventory_tool", inventory_tool_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    # Memory steps (Milestone 8, Part 1) -- see memory_nodes.py.
    builder.add_node("check_pending", check_pending_node)
    builder.add_node("load_memory", load_memory_node)
    builder.add_node("self_evaluate", self_evaluate_node)

    builder.add_edge(START, "receive_question")
    builder.add_edge("receive_question", "check_pending")
    # A message that only answers a memory proposal ("yes") has nothing else
    # to look up, so it skips straight to the end.
    builder.add_conditional_edges(
        "check_pending",
        route_after_decision,
        {"load_memory": "load_memory", "self_evaluate": "self_evaluate"},
    )
    builder.add_conditional_edges(
        "load_memory",
        route_question,
        {"ticket_tool": "ticket_tool", "inventory_tool": "inventory_tool", "retrieve": "retrieve"},
    )
    # Every branch route_question can choose feeds into the same node --
    # generate waits for all of them (LangGraph's own fan-in behavior:
    # a node with multiple incoming edges from one superstep's parallel
    # dispatch runs only once all of them have completed).
    builder.add_edge("ticket_tool", "generate")
    builder.add_edge("inventory_tool", "generate")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", "self_evaluate")
    builder.add_edge("self_evaluate", END)
    return builder


# Opened once, for the lifetime of the process -- see Part 1's original
# note here for why this is entered manually rather than via `with`.
_checkpointer_cm = SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
_checkpointer = _checkpointer_cm.__enter__()

graph: CompiledStateGraph = build_graph().compile(checkpointer=_checkpointer)


def get_trace(config: dict) -> list[dict]:
    """The ordered list of node executions for one run, read back from
    the checkpoint file after the fact. Each step's "node" is a single
    name, or several joined with " + " when route_question dispatched
    more than one in parallel (e.g. "ticket_tool + retrieve") -- an
    earlier version of this function only ever reported the first of a
    parallel pair, silently dropping the other from the trace, which
    would have made "the trace must clearly show whether the RAG, a
    tool, or both were used" impossible to actually verify from it."""
    history = list(graph.get_state_history(config))
    history.reverse()
    trace = []
    for prev, curr in zip(history, history[1:]):
        node_name = " + ".join(prev.next) if prev.next else "?"
        changed = {k: v for k, v in curr.values.items() if prev.values.get(k) != v}
        trace.append({"node": node_name, "output": changed})
    return trace
