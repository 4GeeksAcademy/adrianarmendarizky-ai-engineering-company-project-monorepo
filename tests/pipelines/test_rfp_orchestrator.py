"""
tests/pipelines/test_rfp_orchestrator.py -- unit tests for the RFP intake
orchestrator (data/pipelines/rfp_intake/orchestrator.py).

The real model is never called. Each test swaps in a fake model that
returns a fixed JSON reply.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake import llm, orchestrator  # noqa: E402

DOC = (
    "Sunset Bay Resorts seeks a concession partner for 3 resorts in Florida. "
    "Estimated annual contract value: $60,000-$75,000 USD. Proposals due Sep 2, 2026."
)


def fake_model(reply: dict):
    def _fake(prompt, *, system=None):
        return json.dumps(reply)
    return _fake


def full_reply(**changes):
    reply = {
        "rfp_id": "SBR-2026-0417",
        "client_name": "Sunset Bay Resorts",
        "location": "Florida",
        "service_type": "co-branded concession",
        "scope": "3 resorts",
        "deadline": "Sep 2, 2026",
        "budget_range": "$60,000-$75,000 USD",
        "departments": {
            "marketing": {"reason": "Brand terms.", "extract": "Sunset Bay Resorts seeks a concession partner"},
            "operaciones": {"reason": "Runs 3 stands.", "extract": "for 3 resorts in Florida"},
        },
        "other_departments_mentioned": [],
    }
    reply.update(changes)
    return reply


def test_normal_result_has_metadata_and_departments(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply()))
    result = orchestrator.orchestrate_rfp(DOC, "en")
    assert result["metadata"]["client_name"] == "Sunset Bay Resorts"
    assert result["metadata"]["language"] == "en"
    assert result["departments_needed"] == ["marketing", "operaciones"]
    assert result["missing_fields"] == []


def test_unknown_department_is_not_routed_but_is_reported(monkeypatch):
    reply = full_reply()
    reply["departments"]["finance"] = {"reason": "Money.", "extract": "x"}
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    result = orchestrator.orchestrate_rfp(DOC)
    assert "finance" not in result["assignments"]
    assert "finance" in result["other_departments_mentioned"]


def test_marketing_is_always_included(monkeypatch):
    reply = full_reply()
    del reply["departments"]["marketing"]
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    result = orchestrator.orchestrate_rfp(DOC)
    assert "marketing" in result["departments_needed"]


def test_departments_come_back_in_a_fixed_order(monkeypatch):
    reply = full_reply()
    reply["departments"] = {
        "training": {"reason": "New menu.", "extract": "for 3 resorts"},
        "procurement": {"reason": "Buy food.", "extract": "for 3 resorts"},
        "marketing": {"reason": "Brand.", "extract": "for 3 resorts"},
    }
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    result = orchestrator.orchestrate_rfp(DOC)
    assert result["departments_needed"] == ["marketing", "procurement", "training"]


def test_missing_budget_is_reported_and_never_invented(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply(budget_range=None)))
    result = orchestrator.orchestrate_rfp(DOC)
    assert result["metadata"]["budget_range"] is None
    assert "budget_range" in result["missing_fields"]


def test_placeholder_answers_count_as_missing(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply(deadline="Not specified")))
    result = orchestrator.orchestrate_rfp(DOC)
    assert result["metadata"]["deadline"] is None
    assert "deadline" in result["missing_fields"]


def test_quoted_extract_is_kept(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply()))
    marketing = orchestrator.orchestrate_rfp(DOC)["assignments"]["marketing"]
    assert marketing["extract_is_verbatim"] is True
    assert marketing["extract"] == "Sunset Bay Resorts seeks a concession partner"


def test_made_up_extract_is_replaced_by_the_full_document(monkeypatch):
    reply = full_reply()
    reply["departments"]["marketing"]["extract"] = "The resort will pay $500,000."
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    marketing = orchestrator.orchestrate_rfp(DOC)["assignments"]["marketing"]
    assert marketing["extract_is_verbatim"] is False
    assert marketing["extract"] == DOC


def test_reply_without_departments_raises(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model({"client_name": "X"}))
    with pytest.raises(llm.LlmJsonError):
        orchestrator.orchestrate_rfp(DOC)


def test_node_reads_state_and_returns_stage_fields(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply()))
    update = orchestrator.orchestrate_node({"markdown": DOC, "language": "es"})
    assert update["metadata"]["language"] == "es"
    assert set(update) == {
        "metadata", "departments_needed", "assignments",
        "missing_fields", "other_departments_mentioned",
    }


BULLET_DOC = (
    "Scope of Work:\n"
    "\u2022 Design and operate a branded concession stand in each of the 3 resort properties\n"
    "\u2022 Estimated annual contract value: $60,000\u2013$75,000 USD\n"
)


def test_extract_with_bullets_dashes_and_line_breaks_still_counts_as_real(monkeypatch):
    reply = full_reply()
    reply["departments"]["marketing"]["extract"] = (
        "Design and operate a branded concession stand in each of the 3 resort properties\n"
        "Estimated annual contract value: $60,000-$75,000 USD"
    )
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    marketing = orchestrator.orchestrate_rfp(BULLET_DOC)["assignments"]["marketing"]
    assert marketing["extract_is_verbatim"] is True


def test_one_made_up_sentence_makes_the_whole_extract_fall_back(monkeypatch):
    reply = full_reply()
    reply["departments"]["marketing"]["extract"] = (
        "Design and operate a branded concession stand in each of the 3 resort properties\n"
        "The resort promises a ten year contract"
    )
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    marketing = orchestrator.orchestrate_rfp(BULLET_DOC)["assignments"]["marketing"]
    assert marketing["extract_is_verbatim"] is False
    assert marketing["extract"] == BULLET_DOC


# --- training: a request for something NEW must reach the training department ----

NEW_MENU_DOC = (
    "Sunset Bay Resorts seeks a concession partner for 3 resorts in Florida. "
    "Develop a co-branded signature menu item exclusive to Sunset Bay Resorts. "
    "Proposals due Sep 2, 2026."
)
STANDARD_MENU_DOC = (
    "Andes Tech Solutions wants weekly lunch for 220 people. "
    "We would like the standard menu you already offer."
)


def test_a_quoted_request_for_something_new_adds_training_even_if_the_model_forgot_it(monkeypatch):
    reply = full_reply(new_item_evidence="Develop a co-branded signature menu item exclusive to Sunset Bay Resorts.")
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    result = orchestrator.orchestrate_rfp(NEW_MENU_DOC)
    assert result["departments_needed"] == ["marketing", "operaciones", "training"]
    training = result["assignments"]["training"]
    assert training["extract"] == "Develop a co-branded signature menu item exclusive to Sunset Bay Resorts."
    assert training["extract_is_verbatim"] is True


def test_a_made_up_quote_does_not_add_training(monkeypatch):
    reply = full_reply(new_item_evidence="The resort wants a brand new recipe book.")
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    result = orchestrator.orchestrate_rfp(NEW_MENU_DOC)
    assert "training" not in result["departments_needed"]


def test_no_quote_means_no_training_for_a_standard_menu_request(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply(new_item_evidence=None)))
    result = orchestrator.orchestrate_rfp(STANDARD_MENU_DOC)
    assert "training" not in result["departments_needed"]


def test_a_reply_without_the_new_field_still_works(monkeypatch):
    # replies from before this change (and the other tests' fakes) have no new_item_evidence
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(full_reply()))
    assert orchestrator.orchestrate_rfp(DOC)["departments_needed"] == ["marketing", "operaciones"]


def test_training_the_model_already_chose_is_not_replaced_or_duplicated(monkeypatch):
    reply = full_reply(new_item_evidence="Develop a co-branded signature menu item exclusive to Sunset Bay Resorts.")
    reply["departments"]["training"] = {
        "reason": "The model's own reason.", "extract": "Develop a co-branded signature menu item"}
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(reply))
    result = orchestrator.orchestrate_rfp(NEW_MENU_DOC)
    assert result["departments_needed"].count("training") == 1
    assert result["assignments"]["training"]["reason"] == "The model's own reason."


def test_the_prompt_asks_for_the_quote_before_the_departments():
    prompt = orchestrator.SYSTEM_PROMPT
    assert "new_item_evidence" in prompt
    assert prompt.index('"new_item_evidence": null') < prompt.index('"departments": {')
