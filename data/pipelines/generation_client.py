"""
data/pipelines/generation_client.py -- the one place the generation LLM is
called from. data/pipelines/rag.py's generate_answer() calls
call_generation_llm(prompt) and nothing else here; tests mock that one
function instead of reaching into an HTTP client.
"""

import os

from openai import OpenAI

GENERATION_BASE_URL = os.environ.get("GENERATION_BASE_URL", "https://llm.4geeks.ai")
GENERATION_MODEL_ID = os.environ.get(
        "GENERATION_MODEL_ID", "downtown-miami/groq/llama-3.1-8b-instant"
)
_client = OpenAI(
    # A placeholder here (instead of None) keeps *importing* this module
    # working before .env has a real key -- the OpenAI SDK raises
    # immediately on construction if api_key is None. The real key is only
    # needed once call_generation_llm() actually runs, and a request made
    # with the placeholder fails loudly with an auth error, not silently.
    api_key=os.environ.get("GENERATION_API_KEY", "not-set"),
    base_url=GENERATION_BASE_URL,
)


def call_generation_llm(prompt: str) -> str:
    """Sends one prompt to the generation model and returns its text
    reply. Kept to this one call in, one string out shape so tests can
    monkeypatch it without knowing anything about the OpenAI SDK."""
    response = _client.chat.completions.create(
        model=GENERATION_MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,  # low but not zero -- natural salesperson phrasing, not creative
    )
    return response.choices[0].message.content
