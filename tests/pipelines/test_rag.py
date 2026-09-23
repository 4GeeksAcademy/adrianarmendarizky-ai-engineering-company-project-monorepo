"""
tests/pipelines/test_rag.py -- unit tests for data/pipelines/rag.py
(retrieve, generate_answer, query). No live Qdrant and no real LLM call
happens anywhere in this file -- that's the point (see the ticket's Phase
5 checklist): a mocked/in-memory stand-in replaces each one.

data/process/rag.py is ALSO named rag.py (different folder, same
filename -- that's what the ticket's file layout asks for), so importing
"rag" the normal way risks pulling in the wrong one depending on sys.path
order. To sidestep that entirely, this file loads
data/pipelines/rag.py by its exact path via importlib, under a module name
that can't collide with anything else.

Run with:
    cd services/api && uv run python -m pytest ../../tests/pipelines/test_rag.py -v
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))  # for dotenv, etc.
sys.path.insert(0, str(REPO_ROOT / "data" / "process"))  # for embeddings.py / rag.py's own imports
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))  # for generation_client.py


def _load(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Loading rag.py constructs a QdrantClient and an OpenAI client, but
# neither of those makes a network call (or needs a real API key) just to
# be constructed -- and embeddings.py's actual model is loaded lazily, on
# embed()'s first real call, not on import. So importing this module here
# needs no live Qdrant server, no downloaded model, and no API key.
# embed(), call_generation_llm(), and the Qdrant client's .search() are
# then replaced per-test below, before anything would really call out.
rag = _load(REPO_ROOT / "data" / "pipelines" / "rag.py", "pipelines_rag")


class _FakeHit:
    """Stands in for one qdrant_client search result: real hits expose
    .payload (dict) and .score (float), which is all retrieve() reads."""

    def __init__(self, payload, score):
        self.payload = payload
        self.score = score


class _FakeQueryResponse:
    """Stands in for query_points()'s return value -- real responses expose
    a .points list of hits like _FakeHit above."""

    def __init__(self, points):
        self.points = points


def _payload(source_document, section, text):
    return {
        "company": "brasaland",
        "source_document": source_document,
        "section": section,
        "language": "en",
        "chunk_index": 0,
        "text": text,
    }


# --- retrieve() -------------------------------------------------------


def test_retrieve_drops_hits_below_min_score():
    response = _FakeQueryResponse(
        [
            _FakeHit(_payload("loyalty-program", "Program tiers", "Gold tier needs 50+ points."), 0.81),
            _FakeHit(_payload("waste-protocol", "Operational target", "Unrelated waste text."), 0.12),
        ]
    )
    with patch.object(rag, "embed", return_value=[0.1, 0.2, 0.3]), patch.object(
        rag._client, "query_points", return_value=response
    ):
        results = rag.retrieve("How many points for Gold tier?", min_score=0.3)

    assert len(results) == 1
    assert results[0]["source_document"] == "loyalty-program"


def test_retrieve_returns_fewer_than_k_when_few_hits_clear_the_bar():
    response = _FakeQueryResponse([_FakeHit(_payload("loyalty-program", "Program tiers", "Gold tier text."), 0.81)])
    with patch.object(rag, "embed", return_value=[0.1, 0.2, 0.3]), patch.object(
        rag._client, "query_points", return_value=response
    ):
        results = rag.retrieve("Gold tier?", k=5, min_score=0.3)

    # Only 1 hit was returned by (mocked) Qdrant at all -- retrieve() must
    # never pad the result up to k with anything else.
    assert len(results) == 1


def test_retrieve_embeds_the_query_with_the_same_embed_used_at_index_time():
    with patch.object(rag, "embed", return_value=[9.0]) as mock_embed, patch.object(
        rag._client, "query_points", return_value=_FakeQueryResponse([])
    ) as mock_query:
        rag.retrieve("does the BBQ Ribs dish have allergens?")

    mock_embed.assert_called_once_with("does the BBQ Ribs dish have allergens?")
    mock_query.assert_called_once()
    assert mock_query.call_args.kwargs["query"] == [9.0]


# --- generate_answer() -------------------------------------------------


def test_generate_answer_returns_fixed_message_on_empty_context_without_calling_the_llm():
    with patch.object(rag, "call_generation_llm") as mock_llm:
        answer = rag.generate_answer("How many points for Gold tier?", context=[])

    mock_llm.assert_not_called()
    assert answer == rag.NO_INFO_MESSAGE


def test_generate_answer_returns_model_output_not_raw_chunk_text():
    context = [_payload("loyalty-program", "Program tiers", "Gold (50+ points): 15% permanent discount.")]
    with patch.object(rag, "call_generation_llm", return_value="You need 50 points to reach Gold.") as mock_llm:
        answer = rag.generate_answer("How many points for Gold tier?", context)

    assert answer == "You need 50 points to reach Gold."
    # The raw chunk text was fed to the LLM as context, not returned as-is.
    assert answer != context[0]["text"]
    prompt_sent = mock_llm.call_args.args[0]
    assert "Gold (50+ points)" in prompt_sent  # the chunk did reach the prompt


# --- query() -------------------------------------------------------


def test_query_is_retrieve_plus_generate_answer_and_nothing_else():
    fake_context = [_payload("loyalty-program", "Program tiers", "Gold tier text.")]
    with patch.object(rag, "retrieve", return_value=fake_context) as mock_retrieve, patch.object(
        rag, "generate_answer", return_value="You need 50 points."
    ) as mock_generate:
        answer = rag.query("How many points for Gold tier?")

    mock_retrieve.assert_called_once_with("How many points for Gold tier?")
    mock_generate.assert_called_once_with("How many points for Gold tier?", fake_context)
    assert answer == "You need 50 points."
