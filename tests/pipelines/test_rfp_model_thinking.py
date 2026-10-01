"""
tests/pipelines/test_rfp_model_thinking.py -- the RFP workflow asks the model
with its hidden "thinking" turned off (a thinking call took almost 6 minutes,
the same call without it 19 seconds). Other callers of the model client are
not affected.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

import generation_client  # noqa: E402
from rfp_intake import llm  # noqa: E402
from rfp_response import generator  # noqa: E402

NO_THINKING = {"reasoning": {"enabled": False}}


class Spy:
    """Stands in for generation_client.call_generation_llm and records the call."""

    def __init__(self, reply='{"ok": true}'):
        self.reply = reply
        self.calls = []

    def __call__(self, prompt, **kwargs):
        self.calls.append(kwargs)
        return self.reply


def test_the_rfp_wrapper_turns_thinking_off_by_default(monkeypatch):
    spy = Spy()
    monkeypatch.setattr(generation_client, "call_generation_llm", spy)
    llm.call_generation_llm("hello", system="be brief")
    assert spy.calls == [{"system": "be brief", "extra_body": NO_THINKING}]


def test_thinking_can_be_turned_back_on_with_a_setting(monkeypatch):
    spy = Spy()
    monkeypatch.setattr(generation_client, "call_generation_llm", spy)
    monkeypatch.setattr(llm, "THINKING_OFF", False)
    llm.call_generation_llm("hello")
    assert spy.calls == [{"system": None, "extra_body": None}]


def test_every_rfp_agent_goes_through_the_wrapper(monkeypatch):
    spy = Spy()
    monkeypatch.setattr(generation_client, "call_generation_llm", spy)

    assert llm.ask_json("a question") == {"ok": True}            # classifier, orchestrator, workers, evaluators
    spy.reply = "## Draft\n- Text."
    generator.generate_draft("operaciones", {"client_name": "X"}, ["aspect"], [])   # the generators

    assert len(spy.calls) == 2
    assert all(call["extra_body"] == NO_THINKING for call in spy.calls)


def test_the_shared_client_sends_extra_body_only_when_asked(monkeypatch):
    sent = []

    class FakeMessage:
        content = "ok"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            sent.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(generation_client, "_client", FakeClient())

    generation_client.call_generation_llm("hi", system="s")                    # an older caller, unchanged
    generation_client.call_generation_llm("hi", extra_body=NO_THINKING)        # the RFP workflow

    assert sent[0]["extra_body"] is None
    assert sent[1]["extra_body"] == NO_THINKING
    assert sent[0]["messages"][0] == {"role": "system", "content": "s"}
