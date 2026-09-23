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

No retrieval, generation, or routing logic lives here -- this route only
ever calls graph.invoke() and get_trace(), the same "the endpoint
contains no business logic" rule routes/knowledge.py already follows for
query(). If a node raises for any reason, the client gets a clean 500
with a short message, never a raw traceback -- the real exception is
still logged server-side, so nothing is lost for debugging; it just isn't
handed to the caller.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import get_trace, graph

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


class AgentQueryRequest(BaseModel):
    question: str


class AgentQueryResponse(BaseModel):
    answer: str
    thread_id: str


class TraceStep(BaseModel):
    node: str
    output: dict


@router.post("/query", response_model=AgentQueryResponse)
def post_agent_query(body: AgentQueryRequest) -> AgentQueryResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = graph.invoke({"question": question}, config)
    except Exception:
        # Logged in full server-side; the client only ever sees this one
        # short, generic message -- never the raw traceback.
        logger.exception("agent graph run failed (thread_id=%s)", thread_id)
        raise HTTPException(status_code=500, detail="The agent could not complete this request.")

    return AgentQueryResponse(answer=result["answer"], thread_id=thread_id)


@router.get("/trace/{thread_id}", response_model=list[TraceStep])
def get_agent_trace(thread_id: str) -> list[TraceStep]:
    trace = get_trace({"configurable": {"thread_id": thread_id}})
    if not trace:
        raise HTTPException(status_code=404, detail="No run found for that thread_id.")
    return trace
