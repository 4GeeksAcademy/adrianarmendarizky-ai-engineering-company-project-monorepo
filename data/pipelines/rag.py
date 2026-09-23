"""
data/pipelines/rag.py -- Milestone 7 (RAG & Knowledge Base): retrieval and
generation.

Three functions, kept as separate steps on purpose (per the ticket, so a
later project -- the LangGraph agent -- can call retrieve() and
generate_answer() as separate steps without re-running retrieval or
re-wrapping the whole query() monolith):

  retrieve(query, k, min_score)      -> list[dict]   searches Qdrant, returns payloads
  generate_answer(question, context) -> str           the ONLY function that calls the LLM
  query(question)                    -> str           retrieve() + generate_answer(), nothing else

services/routers/knowledge.py is the only thing outside this file (and its
own tests) that should ever call query() -- see that file for the
POST /knowledge/query endpoint.

Run standalone for a quick manual check (requires setup() to have already
been run -- see data/process/rag.py):
    cd services/api && uv run python -c "
    import sys; sys.path.insert(0, '../../data/pipelines')
    from rag import query
    print(query('How many points do I need for Gold tier?'))
    "
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
# NOTE: this intentionally does NOT put data/process/ on sys.path and does
# NOT `import rag` from there -- data/process/rag.py is also named rag.py,
# and this file *is* data/pipelines/rag.py, so a same-name cross-import
# between the two is one bad `sys.path` order away from silently importing
# the wrong module. QDRANT_COLLECTION/QDRANT_URL are duplicated below
# instead (two constants -- cheaper to keep in sync by hand than to risk
# that collision). embed() is the one thing actually shared, and it lives
# in its own embeddings.py, not in rag.py, for exactly this reason.
sys.path.insert(0, str(REPO_ROOT / "data" / "process"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "services" / "api" / ".env")

from qdrant_client import QdrantClient  # noqa: E402

from embeddings import embed  # noqa: E402
from generation_client import call_generation_llm  # noqa: E402

QDRANT_COLLECTION = "brasaland_knowledge"  # must match data/process/rag.py
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

# Measured against data/eval/test-queries.json (10/10 Recall@3):
# every correct hit scored >= 0.285, and the only two wrong-document hits
# in the whole run both scored exactly 0.254 -- 0.27 sits in that gap.
# See docs/rag/rag-design.md section 4 for the full numbers.
DEFAULT_MIN_SCORE = 0.27
DEFAULT_K = 5

_client = QdrantClient(url=QDRANT_URL)

# Shown to the person asking when nothing in the knowledge base clears
# min_score. Fixed and never touches the LLM, so it can never invent an
# answer when retrieval comes up empty -- the ticket's Faithfulness KPI.
NO_INFO_MESSAGE = (
    "I don't have enough information in the Brasaland knowledge base to answer that. "
    "Please check with your manager or the relevant department."
)


def retrieve(query: str, *, k: int = DEFAULT_K, min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    """Embeds `query` with the same embed() used at index time, searches
    the brasaland_knowledge Qdrant collection for the top-k nearest chunks,
    and returns the payloads of every hit scoring at or above min_score
    (fewer than k if the rest don't clear the bar -- never padded).
    Each returned dict is a chunk's payload plus a "score" key."""
    vector = embed(query)
    # query_points() is qdrant-client's current search API (the older
    # .search() method is gone as of qdrant-client 1.10+). score_threshold
    # asks the server to do the same >= min_score filtering already, but
    # the explicit Python-side filter below is kept as the real guarantee
    # -- it's what the unit tests exercise, and it holds even if a client
    # version stops honoring score_threshold.
    response = _client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        limit=k,
        score_threshold=min_score,
    )
    return [{**hit.payload, "score": hit.score} for hit in response.points if hit.score >= min_score]


def generate_answer(question: str, context: list[dict]) -> str:
    """The only function that calls the generation LLM. Builds a prompt
    from the retrieved chunks and asks the model to answer the way a
    trained Brasaland salesperson would -- confidently, using only the
    given context, in the same language as the question. If context is
    empty, returns NO_INFO_MESSAGE without ever calling the LLM: no
    retrieved chunks means there is nothing to generate from, so this is
    the one path that's structurally incapable of inventing a fact."""
    if not context:
        return NO_INFO_MESSAGE

    context_block = "\n\n".join(
        f"[{chunk['source_document']} - {chunk['section']}]\n{chunk['text']}" for chunk in context
    )
    prompt = f"""You are answering on behalf of Brasaland, a grilled-food restaurant chain,
in the voice of a trained, confident salesperson -- a location manager,
coordinator, or account manager would ask you this, not a search engine.

Answer ONLY using the context below. Do not add any fact, number, or
percentage that isn't in it. If the context doesn't fully answer the
question, say so plainly rather than guessing.

Never claim "zero risk" of anything (e.g. allergen cross-contamination) --
if the context itself doesn't guarantee zero risk, neither should you.

Answer in the same language as the question below.

Context:
{context_block}

Question: {question}

Answer:"""
    return call_generation_llm(prompt)


def query(question: str) -> str:
    """The only function services/routers/knowledge.py should call.
    Literally retrieve() + generate_answer() -- no logic of its own, so a
    later agent can reuse either half without going through this."""
    context = retrieve(question)
    return generate_answer(question, context)
