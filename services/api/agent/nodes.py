"""
services/api/agent/nodes.py -- Part 1 of 2 (LangGraph migration): the
graph's four nodes, plus the one conditional-routing function.

Each node has exactly one job, per the ticket's single-responsibility
requirement:
    receive_question_node  -- normalizes the graph's starting state
    retrieve_node           -- calls retrieve() (data/pipelines/rag.py), nothing else
    generate_node            -- calls generate_answer() (same file), nothing else
    no_info_node              -- returns the honest "not enough information"
                                  answer directly, without ever calling
                                  the generation LLM

retrieve() and generate_answer() are imported from the existing RAG
project, not reimplemented here -- same functions the plain
POST /knowledge/query endpoint already uses. This module deliberately
never imports or calls query() (the retrieve+generate wrapper): doing so
here would re-collapse the two steps the ticket explicitly wants kept
separate and traceable.
"""

import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[3]
# Same hand-rolled sys.path pattern routes/knowledge.py already uses to
# reach data/pipelines/rag.py, which isn't its own installable package.
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rag import retrieve, generate_answer, NO_INFO_MESSAGE  # noqa: E402

from .state import AgentState


def receive_question_node(state: AgentState) -> dict:
    """Entry node: initializes the fields later nodes fill in. Trivial on
    purpose -- input validation (rejecting an empty question) stays in
    the HTTP route, before the graph is ever invoked, since that's
    request handling, not an agent decision. This node exists so
    "receiving the question" is its own traceable step, per the ticket."""
    return {"context": None, "answer": None}


def retrieve_node(state: AgentState) -> dict:
    """Calls the exact retrieve() the RAG endpoint uses -- same
    embedding, same Qdrant collection, same DEFAULT_MIN_SCORE."""
    context = retrieve(state["question"])
    return {"context": context}


def route_after_retrieve(state: AgentState) -> Literal["generate", "no_info"]:
    """The graph's real conditional edge, based on retrieve_node's
    output: if nothing cleared the similarity threshold, route straight
    to an honest answer instead of ever calling the generation node --
    the ticket's explicit example of what a condition (not a hardcoded
    straight line) should look like here."""
    return "generate" if state["context"] else "no_info"


def generate_node(state: AgentState) -> dict:
    """Calls generate_answer(question, context) directly -- never
    query(), which would silently re-run retrieve() a second time and
    hide the retrieve/generate split this graph exists to make explicit."""
    answer = generate_answer(state["question"], state["context"])
    return {"answer": answer}


def no_info_node(state: AgentState) -> dict:
    """Reuses the exact NO_INFO_MESSAGE constant from
    data/pipelines/rag.py -- so the agent and the plain RAG endpoint say
    the same thing when nothing relevant was found -- and never touches
    the generation LLM. Only reachable when route_after_retrieve sends
    the run here, i.e. only when context is empty."""
    return {"answer": NO_INFO_MESSAGE}
