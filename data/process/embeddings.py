"""
data/process/embeddings.py -- the one place embed() is defined.

data/process/rag.py's setup() calls this for every chunk at index time;
data/pipelines/rag.py's retrieve() calls it for the user's question at
query time. Keeping it in its own module (instead of inline in rag.py)
is what makes it trivial to swap the embeddings model without touching
either of those two files -- the ticket's "swap out any piece" requirement.

Default provider: "local", via fastembed (a small, free, local ONNX
embeddings library -- no API key, no per-call cost, and it's what Qdrant's
own client integrates with natively). Model: BAAI/bge-small-en-v1.5,
384 dimensions.

IMPORTANT -- confirm before you submit: the ticket says to "prefer the
free embeddings model provided by 4Geeks for AI Engineering students."
Check your course platform/lesson for that resource's exact model ID and
base URL. If it's an OpenAI-compatible endpoint (most are), set
EMBEDDING_PROVIDER=openai below and fill in the three EMBEDDING_* variables
-- nothing else in this file, or in rag.py/data/pipelines/rag.py, needs to
change. If it turns out to also be fastembed/local, you can leave the
default provider as-is and just double-check EMBEDDING_MODEL_ID matches.
"""

import os

EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local")  # "local" | "openai"

if EMBEDDING_PROVIDER == "local":
    from fastembed import TextEmbedding

    EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "BAAI/bge-small-en-v1.5")
    EMBEDDING_DIM = 384  # bge-small-en-v1.5's output size; update if you change the model

    _model = None  # loaded lazily -- see _get_model()

    def _get_model():
        # Deferred instead of loading at import time: fastembed downloads
        # the ONNX model on first use, which importing this module should
        # never trigger by itself (e.g. a test that mocks embed() directly
        # should never need network access just to import it).
        global _model
        if _model is None:
            _model = TextEmbedding(model_name=EMBEDDING_MODEL_ID)
        return _model

    def embed(text: str) -> list[float]:
        """Embeds one string, using the local fastembed model (loaded on
        first call). Returns a plain list[float] (Qdrant's
        PointStruct/search take either a list or an ndarray, but a list
        keeps this function's return type simple regardless of provider)."""
        (vector,) = _get_model().embed([text])
        return vector.tolist()

elif EMBEDDING_PROVIDER == "openai":
    from openai import OpenAI

    EMBEDDING_MODEL_ID = os.environ.get(
        "EMBEDDING_MODEL_ID", "downtown-miami/openrouter/perplexity/pplx-embed-v1-0.6b"
    )
    EMBEDDING_DIM = int(os.environ["EMBEDDING_DIM"])  # no safe default -- must be measured, see below
    _client = OpenAI(
        api_key=os.environ["EMBEDDING_API_KEY"],
        base_url=os.environ.get("EMBEDDING_BASE_URL", "https://llm.4geeks.ai"),
    )

    def embed(text: str) -> list[float]:
        """Embeds one string via an OpenAI-compatible /embeddings endpoint."""
        response = _client.embeddings.create(model=EMBEDDING_MODEL_ID, input=text)
        return response.data[0].embedding

else:
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER!r}")
