"""
tests/pipelines/test_rfp_classifier.py -- unit tests for the RFP intake
classifier (data/pipelines/rfp_intake/classifier.py).

The real model is never called. Each test swaps in a fake model that
returns a fixed reply, then checks what the classifier does with it.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake import classifier, llm  # noqa: E402


def fake_model(reply):
    """Build a fake call_generation_llm that always answers with `reply`."""
    def _fake(prompt, *, system=None):
        return reply
    return _fake


def test_formal_english_rfp_is_accepted(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '{"is_rfp": true, "reason": "Resort asks for a co-branded concession."}'))
    result = classifier.classify_rfp("REQUEST FOR PROPOSAL Sunset Bay Resorts ...")
    assert result["is_rfp"] is True


def test_informal_spanish_email_is_accepted(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '{"is_rfp": true, "reason": "Company wants weekly catering for 220 people."}'))
    result = classifier.classify_rfp("Hola, somos Andes Tech Solutions ...")
    assert result["is_rfp"] is True


def test_franchise_question_is_rejected_with_a_reason(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '{"is_rfp": false, "reason": "General franchise question, no scope."}'))
    result = classifier.classify_rfp("Quería preguntar si manejan franquicias ...")
    assert result["is_rfp"] is False
    assert "franchise" in result["reason"].lower()


def test_json_wrapped_in_code_fences_is_understood(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '```json\n{"is_rfp": true, "reason": "ok"}\n```'))
    assert classifier.classify_rfp("anything")["is_rfp"] is True


def test_reply_that_is_not_json_raises_instead_of_discarding(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model("Sure! I think it is an RFP."))
    with pytest.raises(llm.LlmJsonError):
        classifier.classify_rfp("anything")


def test_is_rfp_must_be_true_or_false(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '{"is_rfp": "maybe", "reason": "unsure"}'))
    with pytest.raises(llm.LlmJsonError):
        classifier.classify_rfp("anything")


def test_node_sets_discard_reason_only_when_rejected(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '{"is_rfp": false, "reason": "Not a request for a proposal."}'))
    rejected = classifier.classify_node({"markdown": "text"})
    assert rejected == {"is_rfp": False, "discard_reason": "Not a request for a proposal."}

    monkeypatch.setattr(llm, "call_generation_llm", fake_model(
        '{"is_rfp": true, "reason": "Valid."}'))
    accepted = classifier.classify_node({"markdown": "text"})
    assert accepted == {"is_rfp": True, "discard_reason": None}


def test_very_long_documents_are_cut_before_sending(monkeypatch):
    seen = {}

    def spy(prompt, *, system=None):
        seen["prompt"] = prompt
        return '{"is_rfp": true, "reason": "ok"}'

    monkeypatch.setattr(llm, "call_generation_llm", spy)
    classifier.classify_rfp("x" * 100000)
    assert len(seen["prompt"]) < classifier.MAX_CHARS + 200
