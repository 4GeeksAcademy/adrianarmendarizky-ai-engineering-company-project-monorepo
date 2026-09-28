"""
tests/pipelines/test_agent_tools.py -- Part 2 of 2 (external tools):
the routing and fallback evals the ticket asks for.

Same category as test_agent.py's evals (not test_rag.py's unit tests):
these run the real compiled graph, which means real Qdrant, a real
generation-model call for the RAG path, and a real call to your own
running incident/inventory APIs for the tool paths. Set
AGENT_SERVICE_USER_ID in services/api/.env before running these (see
the ticket_tool test's docstring) -- everything else needed is already
in .env from Part 1.

Run with:
    uv run python -m pytest ../../tests/pipelines/test_agent_tools.py -v
"""

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from agent.graph import get_trace, graph  # noqa: E402

# CONFIRM THESE against your own seeded incident data before running --
# EXISTING_TICKET_ID must be a real id from GET /api/incidents (list one
# to check); NONEXISTENT_TICKET_ID just needs to not collide with a real
# one, which an very large id reliably won't.
EXISTING_TICKET_ID = 1
NONEXISTENT_TICKET_ID = 888888

POLICY_QUESTION = "How many points do I need for Gold tier?"


def _run(question: str) -> tuple[dict, list[dict]]:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"question": question}, config)
    return result, get_trace(config)


def test_ticket_question_routes_to_ticket_tool_not_rag():
    """REQUIRED eval 1: a question about a specific ticket must resolve
    through ticket_tool -- retrieve (the RAG) must never run for this
    question, since ticket status is live operational data, not the
    kind of stable knowledge the RAG indexes (see graph.py's docstring)."""
    _, trace = _run(f"What is the status of ticket {EXISTING_TICKET_ID}?")
    nodes_run = " ".join(step["node"] for step in trace)

    assert "ticket_tool" in nodes_run
    assert "retrieve" not in nodes_run


def test_policy_question_routes_to_rag_not_ticket_tool():
    """REQUIRED eval 2: a policy question must resolve through the RAG
    -- ticket_tool (and inventory_tool) must never run for a question
    with no ticket-ID or stock/inventory signal in it at all."""
    _, trace = _run(POLICY_QUESTION)
    nodes_run = " ".join(step["node"] for step in trace)

    assert "retrieve" in nodes_run
    assert "ticket_tool" not in nodes_run
    assert "inventory_tool" not in nodes_run


def test_ticket_fallback_when_ticket_does_not_exist():
    """Fallback eval (optional per the ticket, included anyway): one of
    the three named triggers -- times out, errors, OR the ticket
    doesn't exist. This one's reliably testable without deliberately
    taking a service down mid-test. The answer must be an honest
    "couldn't find it" message, never a fabricated status."""
    result, trace = _run(f"What is the status of ticket {NONEXISTENT_TICKET_ID}?")
    nodes_run = " ".join(step["node"] for step in trace)

    assert "ticket_tool" in nodes_run
    assert str(NONEXISTENT_TICKET_ID) in result["answer"]
    assert "couldn't find" in result["answer"].lower()


def test_compound_question_uses_both_ticket_tool_and_rag():
    """Bonus, beyond the ticket's minimum: the "or both" case explicitly
    -- a question that's genuinely both a ticket lookup and a policy
    question resolves through both sources in the same run, and the
    trace shows them running together (parallel, in the same step), not
    as two separate sequential runs."""
    question = f"What is the status of ticket {EXISTING_TICKET_ID}, and how many points do I need for Gold tier?"
    result, trace = _run(question)
    nodes_run = [step["node"] for step in trace]

    assert any("ticket_tool" in n and "retrieve" in n for n in nodes_run), (
        f"expected one step running both in parallel, got: {nodes_run}"
    )
    assert "50" in result["answer"]


def test_inventory_question_routes_to_inventory_tool():
    """Stretch-goal eval: an inventory question resolves through
    inventory_tool, not the RAG. Uses whatever product genuinely exists
    in your seeded inventory data -- adjust PRODUCT_NAME below if this
    doesn't match your own seed script's data."""
    PRODUCT_NAME = "brisket"  # lowercase substring match against real product names
    _, trace = _run(f"Do we have any {PRODUCT_NAME} in stock?")
    nodes_run = " ".join(step["node"] for step in trace)

    assert "inventory_tool" in nodes_run
