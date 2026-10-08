"""
services/api/agent/nodes.py -- Part 2 of 2 (external tools): adds the
ticket and inventory tool nodes, question-based routing between RAG and
tools, and a generate_node that fans in whatever combination of sources
this run actually used.

Why there's no more separate no_info node (Part 1 had one): route_question
can dispatch to more than one node in parallel (e.g. a ticket tool AND
the RAG, for a compound question). Tested directly against this exact
LangGraph version: a conditional edge evaluated for one parallel branch
cannot see a sibling branch's state write from the same superstep -- so
a decision like "did the ticket tool already succeed?" is not reliably
answerable from a conditional edge sitting right after retrieve. The
only node guaranteed to see every parallel branch's writes, merged, is
one that all of them feed into -- so that's where the "did we actually
find anything, anywhere?" decision has to live now: inside generate_node
itself, not in a routing function. generate_node still never calls the
generation LLM when nothing was found -- that property is preserved,
just enforced one level down from where it was in Part 1.

retrieve() and generate_answer() are still reused unchanged from
data/pipelines/rag.py, exactly as in Part 1 -- this file only adds to
what routes to them and what happens after.

Ticket and inventory lookups no longer talk to those systems directly:
they go through the company's MCP server as an MCP client (see
mcp_client.py). The direct implementation was removed, so there is only
one path.
"""

import re
import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rag import retrieve, generate_answer, NO_INFO_MESSAGE  # noqa: E402

from . import mcp_client
from .guardrails import patterns as guard_patterns
from .guardrails import telemetry as guard_telemetry
from langgraph.config import get_config, get_stream_writer
from .state import AgentState

# --- Question understanding (shared between routing and the tool nodes) --

# Matches "ticket 482", "ticket #482", "incident 482", "ticket ID 482",
# etc. -- both words because the user-facing brief says "ticket" while
# the actual system is called the incident manager.
_TICKET_ID_RE = re.compile(r"\b(?:ticket|incident)s?\D{0,12}?(\d+)", re.IGNORECASE)

_INVENTORY_TRIGGER_RE = re.compile(r"\b(stock|inventory)\b", re.IGNORECASE)

# A deliberately explicit, code-reviewable list rather than an LLM-based
# router: this graph's whole point (per the ticket) is that routing is
# traceable and testable. Terms drawn from the RAG's own 4 source docs
# (loyalty/waste/allergens/supplier-ordering).
_POLICY_KEYWORDS = (
    "point", "loyalty", "gold", "silver", "bronze", "tier", "discount",
    "allerg", "gluten", "dairy", "nut", "cross-contamination",
    "waste", "shrinkage", "expir",
    "supplier", "delivery", "order", "protocol", "policy",
)


def extract_ticket_id(question: str) -> int | None:
    match = _TICKET_ID_RE.search(question)
    return int(match.group(1)) if match else None


def wants_inventory(question: str) -> bool:
    return bool(_INVENTORY_TRIGGER_RE.search(question))


def _mentions_policy_topic(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _POLICY_KEYWORDS)


def route_question(state: AgentState) -> list[str]:
    """The agent's one routing decision: which of [ticket_tool,
    inventory_tool, retrieve] this question needs -- possibly more than
    one, run in parallel, which is what makes "or both" (the ticket's
    own phrase) possible. Falls back to the RAG when nothing else
    matched, since that's what every question needs by default absent a
    tool-specific signal."""
    targets: list[str] = []
    if extract_ticket_id(state["question"]) is not None:
        targets.append("ticket_tool")
    if wants_inventory(state["question"]):
        targets.append("inventory_tool")
    if not targets or _mentions_policy_topic(state["question"]):
        targets.append("retrieve")
    return targets


# --- Nodes --------------------------------------------------------------


def receive_question_node(state: AgentState) -> dict:
    """Entry node: initializes every field later nodes may fill in.
    Input validation (rejecting an empty question) stays in the HTTP
    route, same as Part 1."""
    return {
        "context": None,
        "ticket_info": None,
        "ticket_error": None,
        "inventory_matches": None,
        "inventory_error": None,
        "answer": None,
        "memory_notes": None,
        "memory_ack": None,
        "memory_handled": False,
        "skip_rest": False,
        "memory_proposal": None,
        "guard_scope": None,
    }


def retrieve_node(state: AgentState) -> dict:
    """Unchanged from Part 1: calls the exact retrieve() the RAG
    endpoint uses."""
    return {"context": retrieve(state["question"])}


_TICKET_UNAVAILABLE = (
    "I couldn't confirm that ticket's status right now -- "
    "the incident system isn't responding. Please try again shortly."
)
_INVENTORY_UNAVAILABLE = (
    "I couldn't check inventory right now -- "
    "the inventory system isn't responding. Please try again shortly."
)


def ticket_tool_node(state: AgentState) -> dict:
    """Looks the ticket up through the MCP server (tool:
    check_ticket_status) -- read-only, with the agent's own read-only
    token. Never fabricates a status: success sets ticket_info, and every
    failure sets a specific, honest ticket_error instead.

    Milestone 8 Part 2 (SEC-114): a malformed tool result (not a dict) is
    a STRUCTURAL guardrail failure -- logged as such, same category the
    ticket's own harness note uses, distinct from a content or security
    failure."""
    ticket_id = extract_ticket_id(state["question"])
    try:
        ticket = mcp_client.call_tool("check_ticket_status", {"ticket_id": ticket_id})
    except mcp_client.MCPToolError as exc:
        if exc.code == "ticket_not_found":
            return {"ticket_error": f"I couldn't find a ticket with ID {ticket_id}."}
        return {"ticket_error": _TICKET_UNAVAILABLE}
    except mcp_client.MCPUnavailableError:
        return {"ticket_error": _TICKET_UNAVAILABLE}
    if not isinstance(ticket, dict):
        guard_telemetry.log_event("structural", "malformed_tool_result", tool="check_ticket_status")
        return {"ticket_error": _TICKET_UNAVAILABLE}
    return {"ticket_info": ticket}


def inventory_tool_node(state: AgentState) -> dict:
    """Reads the product list through the MCP server (tool:
    query_inventory), then matches real product names against the
    question -- the same matching as before, just over data that now
    arrives through the MCP server. An empty match is a legitimate
    result, reported honestly rather than treated as an error."""
    try:
        products = mcp_client.call_tool("query_inventory", {})
    except (mcp_client.MCPToolError, mcp_client.MCPUnavailableError):
        return {"inventory_error": _INVENTORY_UNAVAILABLE}
    if not isinstance(products, list):
        # Milestone 8 Part 2 (SEC-114): a malformed tool result is a
        # STRUCTURAL guardrail failure -- see ticket_tool_node above.
        guard_telemetry.log_event("structural", "malformed_tool_result", tool="query_inventory")
        return {"inventory_error": _INVENTORY_UNAVAILABLE}
    question = state["question"].lower()
    matches = [p for p in products if p["name"].lower() in question]
    if not matches:
        return {"inventory_error": "I couldn't find a matching product in inventory for that question."}
    return {"inventory_matches": matches}


def _format_ticket_answer(ticket: dict) -> str:
    """Milestone 8 Part 2 (SEC-114): the ticket's title and category are
    text someone else typed when they filed the ticket, so before it is
    shown to a DIFFERENT person asking about it, it goes through the same
    isolation layer as a RAG chunk or a manager note (guardrails/patterns.py).
    There is no LLM in this path -- a ticket's status is formatted directly,
    never generated -- so there is nothing here for an injected phrase to
    manipulate, but the raw text would otherwise still reach the user
    unfiltered."""
    title, title_flagged = guard_patterns.sanitize_external_content(ticket["title"])
    category, category_flagged = guard_patterns.sanitize_external_content(ticket["category"])
    if title_flagged or category_flagged:
        guard_telemetry.log_event("security", "poisoned_tool_content", tool="check_ticket_status",
                                  ticket_id=ticket.get("id"))
    return (
        f"Ticket #{ticket['id']} ({title}): status {ticket['status']}, "
        f"category {category}, branch {ticket['branch']} "
        f"(last updated {ticket['updated_at']})."
    )


def _format_inventory_answer(matches: list[dict]) -> str:
    """Same isolation as _format_ticket_answer above, applied to each
    product name."""
    lines = []
    flagged_any = False
    for m in matches:
        name, was_flagged = guard_patterns.sanitize_external_content(m["name"])
        flagged_any = flagged_any or was_flagged
        lines.append(f"{name}: {m['current_stock']} units in stock.")
    if flagged_any:
        guard_telemetry.log_event("security", "poisoned_tool_content", tool="query_inventory")
    return " ".join(lines)


def _token_writer():
    """Real-Time Systems Part 2: the WebSocket chat starts the graph with
    configurable stream_tokens=True and reads LangGraph's "custom" stream.
    Returns a function that sends one piece of the answer to that stream, or
    None for every other caller (POST /agent/query, tests), which is how the
    node behaves exactly as before when nobody is streaming."""
    try:
        if get_config().get("configurable", {}).get("stream_tokens"):
            return get_stream_writer()
    except RuntimeError:  # called outside a graph run
        pass
    return None


def generate_node(state: AgentState) -> dict:
    """The fan-in node: assembles the final answer from whichever
    sources route_question actually invoked, however many ran. A ticket
    or inventory result is formatted directly (no LLM call, no
    hallucination risk on structured data); the RAG portion still goes
    through generate_answer() exactly as in Part 1, and only runs when
    there's real context to reason over. If nothing this run tried
    produced anything at all, the answer is NO_INFO_MESSAGE -- the same
    fixed string Part 1 used, reused here rather than duplicated."""
    write = _token_writer()
    parts = []

    if state.get("ticket_info"):
        parts.append(_format_ticket_answer(state["ticket_info"]))
        if write:
            write({"token": parts[-1] + "\n\n"})
    elif state.get("ticket_error"):
        parts.append(state["ticket_error"])
        if write:
            write({"token": parts[-1] + "\n\n"})

    if state.get("inventory_matches"):
        parts.append(_format_inventory_answer(state["inventory_matches"]))
        if write:
            write({"token": parts[-1] + "\n\n"})
    elif state.get("inventory_error"):
        parts.append(state["inventory_error"])
        if write:
            write({"token": parts[-1] + "\n\n"})

    # Saved manager notes (agent/memory_nodes.py) are added to the RAG answer.
    # If the question matched no documents and no tool answered it, the notes
    # alone can still answer it (e.g. "when does the Medellin meat supplier
    # deliver?" after a manager corrected the day).
    #
    # Milestone 8 Part 2 (SEC-114): both the retrieved context and the saved
    # notes came from outside our own code (a document in the knowledge base;
    # a fact a manager typed), so both go through the isolation layer before
    # they can reach the generation prompt -- a poisoned document or note is
    # withheld rather than passed through as if it were trustworthy, and the
    # attempt is logged. This is what "content from a tool or a RAG document
    # must never be treated as a system instruction" actually means in code.
    context = state.get("context") or []
    memory_notes = state.get("memory_notes") or []
    if context or memory_notes:
        context, flagged_chunks = guard_patterns.sanitize_chunks(context)
        memory_notes, flagged_notes = guard_patterns.sanitize_notes(memory_notes)
        for source in flagged_chunks:
            guard_telemetry.log_event("security", "poisoned_rag_content", source_document=source)
        for excerpt in flagged_notes:
            guard_telemetry.log_event("security", "poisoned_memory_note", excerpt=excerpt)
    if context or (memory_notes and not parts):
        if write:
            parts.append(generate_answer(
                state["question"], context, memory_notes or None,
                on_token=lambda piece: write({"token": piece}),
            ))
        else:  # not streaming: the exact call this node always made
            parts.append(generate_answer(state["question"], context, memory_notes or None))

    if not parts:
        parts.append(NO_INFO_MESSAGE)
        if write:
            write({"token": NO_INFO_MESSAGE})

    return {"answer": "\n\n".join(parts)}
