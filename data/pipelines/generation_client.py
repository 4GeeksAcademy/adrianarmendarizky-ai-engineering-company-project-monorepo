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
    "GENERATION_MODEL_ID", "downtown-miami/openrouter/deepseek/deepseek-v4-flash")
_client = OpenAI(
    # A placeholder here (instead of None) keeps *importing* this module
    # working before .env has a real key -- the OpenAI SDK raises
    # immediately on construction if api_key is None. The real key is only
    # needed once call_generation_llm() actually runs, and a request made
    # with the placeholder fails loudly with an auth error, not silently.
    api_key=os.environ.get("GENERATION_API_KEY", "not-set"),
    base_url=GENERATION_BASE_URL,
)


def call_generation_llm(
    prompt: str, *, system: str | None = None, extra_body: dict | None = None
) -> str:
    """Sends one prompt to the generation model and returns its text
    reply. Kept to this one call in, one string out shape so tests can
    monkeypatch it without knowing anything about the OpenAI SDK.

    system (optional, Milestone 8 Part 2 / SEC-114): when given, sent as
    a genuine system-role message, separate from the user-role prompt --
    real message-role separation, backing up the code-level separation
    the rest of the guardrail harness does (agent/guardrails/). Omitted
    (the default) preserves the exact single-message behavior every
    existing caller (rag.py before this ticket, agent/memory/llm_steps.py)
    already relies on."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = _client.chat.completions.create(
        model=GENERATION_MODEL_ID,
        messages=messages,
        temperature=0.2,  # low but not zero -- natural salesperson phrasing, not creative
        # Extra request settings for the model service (the RFP workflow uses it to
        # turn the model's hidden "thinking" off). None, the default, sends nothing extra.
        extra_body=extra_body,
    )
    return response.choices[0].message.content


def stream_generation_llm(
    prompt: str, *, system: str | None = None, extra_body: dict | None = None
):
    """Same request as call_generation_llm, but yields the reply a few words
    at a time instead of returning it whole (Real-Time Systems, Part 2: the
    WebSocket chat shows tokens as they are generated).

    A generator: when the caller stops early (an interrupt), closing it also
    closes the connection to the model, so no more tokens are produced."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    stream = _client.chat.completions.create(
        model=GENERATION_MODEL_ID,
        messages=messages,
        temperature=0.2,
        extra_body=extra_body,
        stream=True,
    )
    try:
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                yield piece
    finally:
        close = getattr(stream, "close", None)
        if close is not None:
            close()
