"""
services/api/agent/state.py -- Part 2 of 2 (external tools): the graph's
state schema, extended from Part 1.

Still no conversation history, for the same reason as Part 1 (see the
git history of this file for that reasoning -- it hasn't changed). What's
new here is one pair of fields per tool: <tool>_info for a successful
result, <tool>_error for an honest failure message. Every field is read
by generate_node (see nodes.py) to assemble the final answer -- nothing
is carried "just in case."
"""

from typing import TypedDict


class AgentState(TypedDict):
    question: str

    # RAG (Part 1, unchanged in shape)
    context: list[dict] | None

    # Ticket tool (Part 2, required)
    ticket_info: dict | None
    ticket_error: str | None

    # Inventory tool (Part 2, stretch)
    inventory_matches: list[dict] | None
    inventory_error: str | None

    answer: str | None

    # Memory (Milestone 8, Part 1) -- see agent/memory_nodes.py.
    # user_id / session_id come in with the request; without both, every
    # memory step is skipped and the agent behaves as before.
    user_id: str | None
    session_id: str | None
    memory_notes: list[str] | None     # saved facts for the locations the question mentions
    memory_ack: str | None             # e.g. "Saved. I'll remember..." for a proposal resolved this turn
    memory_handled: bool               # a pending proposal was resolved/edited this turn
    skip_rest: bool                    # the message was only a yes/no: go straight to the end
    memory_proposal: dict | None       # the new proposal opened this turn, if any

    # Guardrail harness (Milestone 8, Part 2 -- ticket SEC-114) -- see
    # agent/guard_nodes.py and agent/guardrails/.
    guard_scope: str | None            # "domain" | "casual" | "personal_task" | "instruction_change"
