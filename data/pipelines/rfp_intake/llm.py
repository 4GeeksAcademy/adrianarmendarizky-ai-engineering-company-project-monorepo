"""
llm.py -- asks the model a question and gets a Python dict back.

Every RFP intake agent uses this instead of calling the model directly.
It wraps call_generation_llm() from data/pipelines/generation_client.py,
which is the one place the model is called from. Tests replace
call_generation_llm in THIS module with a fake.

If the model's reply is not valid JSON we raise LlmJsonError. We never
guess: a wrong guess here could wrongly discard a real RFP.
"""

import json
import os
import re

import generation_client

# The model's hidden "thinking" is turned OFF for the RFP workflow. With it on,
# one analysis call spent almost 6 minutes producing 32,000 characters of
# thinking text before writing a 2,000-character answer; with it off the same
# call took 19 seconds. Set RFP_MODEL_THINKING=on in .env to turn it back on.
THINKING_OFF = os.environ.get("RFP_MODEL_THINKING", "off").strip().lower() != "on"
NO_THINKING = {"reasoning": {"enabled": False}}


def call_generation_llm(prompt: str, *, system: str | None = None) -> str:
    """The one place every RFP agent asks the model. Tests replace THIS function."""
    extra = NO_THINKING if THINKING_OFF else None
    return generation_client.call_generation_llm(prompt, system=system, extra_body=extra)


class LlmJsonError(ValueError):
    """The model did not answer with the JSON we asked for."""


def ask_json(prompt: str, *, system: str | None = None) -> dict:
    raw = call_generation_llm(prompt, system=system)
    text = (raw or "").strip()

    # Models sometimes wrap JSON in ```json ... ``` fences. Remove them.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last try: pull out the first {...} block if there is extra text around it.
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise LlmJsonError(f"Model reply was not JSON: {text[:200]!r}")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise LlmJsonError(f"Model reply was not valid JSON: {text[:200]!r}")

    if not isinstance(data, dict):
        raise LlmJsonError(f"Expected a JSON object, got: {text[:200]!r}")
    return data
