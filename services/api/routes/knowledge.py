"""
routes/knowledge.py -- Milestone 7 (RAG & Knowledge Base): the one HTTP
endpoint a salesperson-facing client calls.

No retrieval or generation logic lives here -- this route is a thin caller
into data/pipelines/rag.py's query(), the same "don't calculate anything
inside the endpoint" rule routes/reporting.py already follows for
data/pipelines/pipeline.py. The response is the generated answer string
only: never the raw Qdrant chunks, never a similarity score (those may be
logged server-side for debugging, but must not reach the client -- see
docs/rag/rag-design.md).

This repo's convention is routes/*.py under services/api (see
routes/reporting.py, routes/suppliers.py, etc.) -- used here instead of
the ticket's indicative "services/routers/" so this endpoint follows the
same pattern as every other one already in this API.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# data/pipelines/rag.py isn't its own installable package -- same
# hand-rolled sys.path pattern already used elsewhere in this repo (see
# data/pipelines/pipeline.py's own docstring) to reach a sibling
# directory from inside services/api.
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rag import query as rag_query  # noqa: E402  (data/pipelines/rag.py)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeQueryRequest(BaseModel):
    question: str


class KnowledgeQueryResponse(BaseModel):
    answer: str


@router.post("/query", response_model=KnowledgeQueryResponse)
def post_knowledge_query(body: KnowledgeQueryRequest) -> KnowledgeQueryResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")
    answer = rag_query(question)
    return KnowledgeQueryResponse(answer=answer)
