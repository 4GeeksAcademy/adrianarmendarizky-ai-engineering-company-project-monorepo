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
"""

import re
import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rag import retrieve, generate_answer, NO_INFO_MESSAGE  # noqa: E402

from . import tools
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
    }


def retrieve_node(state: AgentState) -> dict:
    """Unchanged from Part 1: calls the exact retrieve() the RAG
    endpoint uses."""
    return {"context": retrieve(state["question"])}


def ticket_tool_node(state: AgentState) -> dict:
    """Calls the real incident manager (tools.lookup_ticket) -- read-only,
    real HTTP, real JWT, real timeout. Never fabricates a status: success
    sets ticket_info, any failure sets a specific, honest ticket_error
    instead."""
    ticket_id = extract_ticket_id(state["question"])
    try:
        result = tools.lookup_ticket(ticket_id)
        return {"ticket_info": result.model_dump()}
    except tools.TicketNotFoundError:
        return {"ticket_error": f"I couldn't find a ticket with ID {ticket_id}."}
    except tools.TicketServiceUnavailableError:
        return {
            "ticket_error": (
                "I couldn't confirm that ticket's status right now -- "
                "the incident system isn't responding. Please try again shortly."
            )
        }


def inventory_tool_node(state: AgentState) -> dict:
    """Calls the real inventory manager (tools.lookup_inventory).
    An empty match list is a legitimate result (see lookup_inventory's
    docstring), reported honestly rather than treated as an error."""
    try:
        matches = tools.lookup_inventory(state["question"])
    except tools.InventoryServiceUnavailableError:
        return {
            "inventory_error": (
                "I couldn't check inventory right now -- "
                "the inventory system isn't responding. Please try again shortly."
            )
        }
    if not matches:
        return {"inventory_error": "I couldn't find a matching product in inventory for that question."}
    return {"inventory_matches": [m.model_dump() for m in matches]}


def _format_ticket_answer(ticket: dict) -> str:
    return (
        f"Ticket #{ticket['id']} ({ticket['title']}): status {ticket['status']}, "
        f"category {ticket['category']}, branch {ticket['branch']} "
        f"(last updated {ticket['updated_at']})."
    )


def _format_inventory_answer(matches: list[dict]) -> str:
    lines = [f"{m['name']}: {m['current_stock']} units in stock." for m in matches]
    return " ".join(lines)


def generate_node(state: AgentState) -> dict:
    """The fan-in node: assembles the final answer from whichever
    sources route_question actually invoked, however many ran. A ticket
    or inventory result is formatted directly (no LLM call, no
    hallucination risk on structured data); the RAG portion still goes
    through generate_answer() exactly as in Part 1, and only runs when
    there's real context to reason over. If nothing this run tried
    produced anything at all, the answer is NO_INFO_MESSAGE -- the same
    fixed string Part 1 used, reused here rather than duplicated."""
    parts = []

    if state.get("ticket_info"):
        parts.append(_format_ticket_answer(state["ticket_info"]))
    elif state.get("ticket_error"):
        parts.append(state["ticket_error"])

    if state.get("inventory_matches"):
        parts.append(_format_inventory_answer(state["inventory_matches"]))
    elif state.get("inventory_error"):
        parts.append(state["inventory_error"])

    if state.get("context"):
        parts.append(generate_answer(state["question"], state["context"]))

    if not parts:
        parts.append(NO_INFO_MESSAGE)

    return {"answer": "\n\n".join(parts)}
