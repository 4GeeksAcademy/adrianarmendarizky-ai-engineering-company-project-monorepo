"""
routes/agent.py -- Part 1 of 2 (LangGraph migration): the HTTP surface
for the compiled agent graph.

Two endpoints:
  POST /agent/query        runs the graph for one question. Returns the
                             answer plus the thread_id that run was
                             checkpointed under -- this coexists with the
                             plain POST /knowledge/query endpoint rather
                             than replacing it.
  GET  /agent/trace/{id}   returns that run's trace after the fact --
                             which nodes ran, in what order, and what
                             each one produced -- read back from the
                             SQLite checkpoint file (agent_checkpoints.db),
                             not from anything held only in memory during
                             the request. This is what makes the trace
                             "queryable after the run," not just printed
                             to a console during it.

Milestone 8 (agent memory) changes this route in three ways:
  - POST /agent/query now requires a login (get_current_user). Memory writes
    have to be traceable to a real person, and an open endpoint would let
    anyone try to plant false "corrections". Only managers and admins get the
    memory features; other users get the plain agent.
  - The request can carry a session_id (a conversation id). Send back the one
    the previous response returned to keep the conversation going -- that is
    how the agent connects "yes" to the proposal it just made. Each run still
    gets its own thread_id for the trace, exactly as before.
  - GET /agent/memory/facts and GET /agent/memory/audit let people read what
    the agent remembers and the log of every proposal and decision.

Milestone 8 Part 2 (SEC-114, guardrail harness) adds two more:
  - The response now reports guard_scope: "domain" for an ordinary answer,
    or which guardrail scope blocked/redirected this message otherwise.
  - GET /agent/guardrails/summary and GET /agent/guardrails/events let
    people read how often each guardrail has fired and the full log behind
    that count -- see agent/guard_nodes.py and agent/guardrails/.

No retrieval, generation, or routing logic lives here -- this route only
ever calls graph.invoke() and get_trace(), the same "the endpoint
contains no business logic" rule routes/knowledge.py already follows for
query(). If a node raises for any reason, the client gets a clean 500
with a short message, never a raw traceback -- the real exception is
still logged server-side, so nothing is lost for debugging; it just isn't
handed to the caller.
"""

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from redis.exceptions import RedisError

from agent.graph import get_trace, graph
from agent.guardrails import telemetry as guard_telemetry
from agent.memory import policy
from agent.memory.store import get_store
from dependencies import get_current_user
from user_models import Role, User

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)

# Who may use agent memory: the location managers it is built for, plus admins.
MEMORY_ROLES = (Role.MANAGER, Role.ADMIN)
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")


class AgentQueryRequest(BaseModel):
    question: str
    # Conversation id. Leave it out to start a new conversation; send back the
    # session_id from the last response to continue one.
    session_id: str | None = None


class PendingProposal(BaseModel):
    proposal_id: str
    location: str
    category: str
    fact: str
    expires_at: str


class AgentQueryResponse(BaseModel):
    answer: str
    thread_id: str
    session_id: str
    # Set when this answer ends with a "do you want me to remember this?" question.
    pending_memory_proposal: PendingProposal | None = None
    # Milestone 8 Part 2 (SEC-114): "domain" for an ordinary answer; otherwise which
    # guardrail scope the input guard classified this message as and answered from.
    guard_scope: str | None = None


class TraceStep(BaseModel):
    node: str
    output: dict


@router.post("/query", response_model=AgentQueryResponse)
def post_agent_query(
    body: AgentQueryRequest, current_user: User = Depends(get_current_user)
) -> AgentQueryResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")
    session_id = body.session_id or uuid.uuid4().hex
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise HTTPException(status_code=422, detail="session_id must be 8-64 letters, digits, - or _")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {"question": question}
    if current_user.role in MEMORY_ROLES:
        graph_input |= {"user_id": str(current_user.id), "session_id": session_id}
    try:
        result = graph.invoke(graph_input, config)
    except Exception:
        # Logged in full server-side; the client only ever sees this one
        # short, generic message -- never the raw traceback.
        logger.exception("agent graph run failed (thread_id=%s)", thread_id)
        raise HTTPException(status_code=500, detail="The agent could not complete this request.")

    proposal = result.get("memory_proposal")
    return AgentQueryResponse(
        answer=result["answer"],
        thread_id=thread_id,
        session_id=session_id,
        pending_memory_proposal=PendingProposal(
            **{k: proposal[k] for k in PendingProposal.model_fields}
        ) if proposal else None,
        guard_scope=result.get("guard_scope"),
    )


@router.get("/trace/{thread_id}", response_model=list[TraceStep])
def get_agent_trace(thread_id: str) -> list[TraceStep]:
    trace = get_trace({"configurable": {"thread_id": thread_id}})
    if not trace:
        raise HTTPException(status_code=404, detail="No run found for that thread_id.")
    return trace


# --- Reading agent memory --------------------------------------------------


@router.get("/memory/facts")
def get_memory_facts(
    location: str | None = Query(default=None, description="e.g. bogota_usaquen or COL-07"),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Everything the agent currently remembers (optionally for one location).
    Managers and admins only."""
    if current_user.role not in MEMORY_ROLES:
        raise HTTPException(status_code=403, detail="Only managers and admins can read agent memory.")
    try:
        if location:
            normalized = policy.normalize_location(location)
            if normalized is None:
                raise HTTPException(status_code=422, detail="not a valid location")
            return get_store().facts_for_location(normalized)
        return get_store().all_facts()
    except RedisError:
        logger.exception("agent memory unavailable")
        raise HTTPException(status_code=503, detail="Agent memory is unavailable right now.")


@router.get("/memory/audit")
def get_memory_audit(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """The append-only log: every proposal, every decision (approved, rejected,
    edited, discarded, expired), every save, removal and blocked attempt, with
    who, what, and when. Admins only."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can read the memory audit log.")
    try:
        return get_store().read_audit(limit=limit, offset=offset)
    except RedisError:
        logger.exception("agent memory unavailable")
        raise HTTPException(status_code=503, detail="Agent memory is unavailable right now.")


# --- Guardrail observability (Milestone 8 Part 2 / SEC-114) ----------------


@router.get("/guardrails/summary")
def get_guardrails_summary(current_user: User = Depends(get_current_user)) -> dict:
    """How many times each guardrail has fired, by category (structural,
    content, security) and by specific reason -- the "simple summary" the
    ticket asks for. Managers and admins only, same bar as memory reads."""
    if current_user.role not in MEMORY_ROLES:
        raise HTTPException(status_code=403, detail="Only managers and admins can read guardrail telemetry.")
    try:
        return guard_telemetry.summary()
    except RedisError:
        logger.exception("guardrail telemetry unavailable")
        raise HTTPException(status_code=503, detail="Guardrail telemetry is unavailable right now.")


@router.get("/guardrails/events")
def get_guardrails_events(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """The full, timestamped log behind the summary above: every guardrail
    block or redirection, with its category and reason. Admins only, same
    bar as the memory audit log."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can read the guardrail event log.")
    try:
        return guard_telemetry.read_events(limit=limit, offset=offset)
    except RedisError:
        logger.exception("guardrail telemetry unavailable")
        raise HTTPException(status_code=503, detail="Guardrail telemetry is unavailable right now.")
