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
