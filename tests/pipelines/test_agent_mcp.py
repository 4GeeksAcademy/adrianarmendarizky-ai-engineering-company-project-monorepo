"""
tests/pipelines/test_agent_mcp.py -- checks for the MCP migration.

1. The agent has no second path to the Incidents or Inventory Managers.
2. When the MCP server can't be reached, the agent answers honestly
   instead of inventing a ticket status.

Like the other agent evals, the second one runs the real compiled graph,
so it needs the same setup as test_agent_tools.py (see the project
notes). Run from services/api:
    uv run python -m pytest ../../tests/pipelines/test_agent_mcp.py -v
"""

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from agent.graph import graph  # noqa: E402

AGENT_DIR = REPO_ROOT / "services" / "api" / "agent"


def test_agent_has_no_direct_path_to_the_incidents_or_inventory_managers():
    """Every ticket/inventory lookup must go through the MCP server. If any
    of these markers of the old direct implementation shows up in the
    agent's code, there are two paths again -- which the ticket forbids."""
    markers = [
        "/api/incidents",
        "/inventory/products",
        "create_access_token",
        "lookup_ticket",
        "lookup_inventory",
    ]
    assert not (AGENT_DIR / "tools.py").exists(), "the old direct tools module is back"
    for path in AGENT_DIR.glob("*.py"):
        text = path.read_text()
        for marker in markers:
            assert marker not in text, f"{path.name} still contains {marker!r}"


def test_ticket_question_gets_an_honest_fallback_when_the_mcp_server_is_unreachable(monkeypatch):
    """Point the agent at a port nothing listens on. The answer must say it
    couldn't confirm the ticket -- not make up a status."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://127.0.0.1:9/mcp")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke({"question": "What is the status of ticket 1?"}, config)
    assert "couldn't confirm" in result["answer"].lower()
