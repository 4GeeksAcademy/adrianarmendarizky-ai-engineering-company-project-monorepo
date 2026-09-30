"""
tests/pipelines/test_rfp_workers.py -- unit tests for the RFP intake
department workers (data/pipelines/rfp_intake/workers.py).

The real model is never called. Each test swaps in a fake model.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake import llm, workers  # noqa: E402

METADATA = {
    "client_name": "Sunset Bay Resorts",
    "budget_range": "$60,000-$75,000 USD",
    "deadline": "Sep 2, 2026",
    "language": "en",
}
EXTRACT = "Design and operate a branded concession stand in each of the 3 resort properties."


def fake_model(reply):
    def _fake(prompt, *, system=None):
        return json.dumps(reply)
    return _fake


def spy_model(reply, seen):
    def _spy(prompt, *, system=None):
        seen["prompt"] = prompt
        seen["system"] = system
        return json.dumps(reply)
    return _spy


@pytest.mark.parametrize("department_id, keyword", [
    ("marketing", "exclusivity"),
    ("operaciones", "capacity"),
    ("procurement", "lead times"),
    ("training", "certified"),
])
def test_each_worker_uses_its_own_instructions(monkeypatch, department_id, keyword):
    seen = {}
    monkeypatch.setattr(llm, "call_generation_llm",
                        spy_model({"key_aspects": ["ok"], "open_questions": []}, seen))
    result = workers.WORKERS[department_id](METADATA, EXTRACT)
    assert result["department_id"] == department_id
    assert keyword in seen["system"]


def test_worker_only_sees_shared_metadata_and_its_own_extract(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "call_generation_llm",
                        spy_model({"key_aspects": ["ok"], "open_questions": []}, seen))
    workers.marketing_worker(METADATA, EXTRACT)
    assert EXTRACT in seen["prompt"]
    assert "Sunset Bay Resorts" in seen["prompt"]
    assert "OTHER DEPARTMENT TEXT" not in seen["prompt"]


def test_returns_key_aspects_and_open_questions(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({
        "key_aspects": ["Runs a concession stand at each resort."],
        "open_questions": ["What are the peak-season opening hours?"],
    }))
    result = workers.operaciones_worker(METADATA, EXTRACT)
    assert result["key_aspects"] == ["Runs a concession stand at each resort."]
    assert result["open_questions"] == ["What are the peak-season opening hours?"]
    assert result["removed_unsupported"] == []


def test_bullet_with_an_invented_number_is_removed_and_reported(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({
        "key_aspects": ["Stands at 3 resorts.", "Needs 500 meals per day."],
        "open_questions": [],
    }))
    result = workers.procurement_worker(METADATA, EXTRACT)
    assert result["key_aspects"] == ["Stands at 3 resorts."]
    assert result["removed_unsupported"] == ["Needs 500 meals per day."]


def test_numbers_from_the_metadata_are_allowed(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({
        "key_aspects": ["Budget is $60,000-$75,000 USD per year.", "Due Sep 2, 2026."],
        "open_questions": [],
    }))
    result = workers.marketing_worker(METADATA, EXTRACT)
    assert len(result["key_aspects"]) == 2
    assert result["removed_unsupported"] == []


def test_numbers_written_as_words_are_fine(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({
        "key_aspects": ["One-year contract using the standard menu."],
        "open_questions": [],
    }))
    result = workers.procurement_worker(METADATA, EXTRACT)
    assert result["key_aspects"] == ["One-year contract using the standard menu."]


def test_lists_are_cleaned_and_capped(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({
        "key_aspects": "A single string, not a list",
        "open_questions": [f"Question {i}?" for i in range(20)] + ["", "  "],
    }))
    result = workers.training_worker(METADATA, EXTRACT)
    assert result["key_aspects"] == ["A single string, not a list"]
    assert len(result["open_questions"]) == workers.MAX_ITEMS


def test_missing_lists_become_empty_lists(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({}))
    result = workers.marketing_worker(METADATA, EXTRACT)
    assert result["key_aspects"] == []
    assert result["open_questions"] == []


def test_unknown_department_is_refused():
    with pytest.raises(ValueError):
        workers.run_worker("finance", METADATA, EXTRACT)


def test_reply_that_is_not_json_raises(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", lambda prompt, *, system=None: "Sure thing!")
    with pytest.raises(llm.LlmJsonError):
        workers.marketing_worker(METADATA, EXTRACT)


def test_worker_sees_deadline_as_proposal_deadline_and_location_as_service_location(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "call_generation_llm",
                        spy_model({"key_aspects": ["ok"], "open_questions": []}, seen))
    workers.operaciones_worker({"deadline": "18 de agosto", "location": "Medellin"}, EXTRACT)
    assert "proposal_deadline" in seen["prompt"]
    assert "service_location" in seen["prompt"]
    assert '"deadline"' not in seen["prompt"]


def test_question_about_offer_validity_is_dropped(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({
        "key_aspects": ["ok"],
        "open_questions": ["How long should the offer remain valid?", "What time is lunch served?"],
    }))
    result = workers.marketing_worker(METADATA, EXTRACT)
    assert result["open_questions"] == ["What time is lunch served?"]
