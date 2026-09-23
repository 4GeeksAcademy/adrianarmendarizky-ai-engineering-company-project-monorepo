"""
services/api/agent/state.py -- Part 1 of 2 (LangGraph migration): the
graph's state schema.

Deliberately minimal: just the question, the retrieved context, and the
answer. No conversation history.

Why no history: this is a single-turn Q&A tool, same as the existing
POST /knowledge/query endpoint it sits beside -- each request already
stands alone (the knowledge-base UI page never sends prior turns, and an
answer only ever needs grounding in the static Brasaland docs, never in
something said earlier in a conversation). Carrying history here would
mean every node has to know how to ignore it, and every caller would have
to start accumulating and re-sending it, for zero grounding benefit. If a
later project adds multi-turn conversation, that's the point to add a
messages field -- not before there's an actual need for one.

Every field below is read by at least one conditional edge or is the
final output; nothing is carried "just in case" (see the module docstring
of graph.py for exactly which node reads/writes which field).
"""

from typing import TypedDict


class AgentState(TypedDict):
    question: str
    # None until retrieve_node runs; [] specifically means "retrieve()
    # ran and found nothing above the similarity threshold" -- that's
    # the exact condition route_after_retrieve branches on.
    context: list[dict] | None
    # None until whichever terminal node (generate or no_info) runs.
    answer: str | None
