"""
tests/pipelines/test_rfp_response_generation.py -- tests for the facts, the
department generators and the evaluators of the RFP response pipeline
(data/pipelines/rfp_response/).

The real model is never called. Each test swaps in a fake model. A fake
decides what to answer by looking at which agent's instructions it received.
"""

import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake import llm  # noqa: E402
from rfp_response import evaluators, facts, generator, rules, settings  # noqa: E402

METADATA = {
    "client_name": "Sunset Bay Resorts, LLC",
    "location": "Florida",
    "service_type": "co-branded concession",
    "scope": "3 resort properties",
    "deadline": "September 2, 2026",
    "budget_range": "$60,000\u2013$75,000 USD",
}
ASPECTS = ["Exclusive concession at 3 resorts.", "Staffing plan for peak season (Nov\u2013Apr)."]
QUESTIONS = ["What are the opening hours?"]

# A draft that follows every guideline for the operaciones department.
GOOD_DRAFT = (
    "## Operations and Delivery\n"
    "- Brasaland will run a concession stand at each of the 3 resort properties.\n"
    "- A staffing plan covers the peak season and the off season.\n"
    "- Kitchen setup takes 10 business days after signing.\n"
    "- The contract value is $60,000 USD (240,000,000 COP) per year.\n"
)


def fake_model(*, draft=GOOD_DRAFT, missing=(), competitors=()):
    """One fake that answers for every agent."""
    def _fake(prompt, *, system=None):
        if "drafting one section" in system:
            return draft
        if "relevance checker" in system:
            return json.dumps({"missing": list(missing)})
        if "competitor checker" in system:
            return json.dumps({"competitors": [{"name": n} for n in competitors]})
        raise AssertionError("unexpected agent")
    return _fake


# --- facts: currency figures -------------------------------------------------

def test_usd_budget_is_converted_to_cop_in_code():
    assert facts.currency_figures(METADATA) == [
        "$60,000 USD = 240,000,000 COP",
        "$75,000 USD = 300,000,000 COP",
    ]


def test_cop_budget_is_converted_to_usd_in_code():
    assert facts.currency_figures({"budget_range": "50.000.000 COP al a\u00f1o"}) == [
        "50,000,000 COP = $12,500 USD"
    ]


@pytest.mark.parametrize("budget", [
    None,
    "",
    "$60,000",                              # currency not stated: never guess
    "$60,000 USD (about 240,000,000 COP)",  # already in both
])
def test_no_conversion_when_the_currency_is_unknown_or_already_both(budget):
    assert facts.currency_figures({"budget_range": budget}) == []


def test_allowed_numbers_cover_the_rfp_the_conversion_and_the_guideline_numbers():
    allowed = facts.allowed_numbers(METADATA, ASPECTS, QUESTIONS)
    assert {"60000", "240000000", "2026", "3", "4000", "10", "30"} <= allowed
    assert "500" not in allowed


def test_shared_details_rename_deadline_and_location():
    details = facts.shared_details(METADATA)
    assert details["proposal_deadline"] == "September 2, 2026"
    assert details["service_location"] == "Florida"
    assert "deadline" not in details and "location" not in details


# --- generators ----------------------------------------------------------------

def capture(monkeypatch, reply=GOOD_DRAFT):
    seen = {}

    def _spy(prompt, *, system=None):
        seen["prompt"], seen["system"] = prompt, system
        return reply

    monkeypatch.setattr(llm, "call_generation_llm", _spy)
    return seen


def test_each_department_has_its_own_generator_instructions(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft("procurement", METADATA, ASPECTS, QUESTIONS)
    assert "Ingredient Costs and Supply" in seen["system"]
    assert "Lucia Fernandez" in seen["system"]
    generator.generate_draft("training", METADATA, ASPECTS, QUESTIONS)
    assert "Training and Certification" in seen["system"]
    assert "Jake Morrison" in seen["system"]


def test_only_marketing_is_told_about_the_pillars_and_offer_validity(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft("marketing", METADATA, ASPECTS, [])
    assert "speed of service" in seen["system"] and "30 days from issuance" in seen["system"]
    generator.generate_draft("operaciones", METADATA, ASPECTS, [])
    assert "speed of service" not in seen["system"]
    assert "10 business days" in seen["system"]  # the setup rule applies to everyone


def test_generator_gets_key_aspects_figures_and_renamed_details_but_no_pdf_text(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft("operaciones", METADATA, ASPECTS, QUESTIONS)
    prompt = seen["prompt"]
    assert "Exclusive concession at 3 resorts." in prompt
    assert "$60,000 USD = 240,000,000 COP" in prompt
    assert "proposal_deadline" in prompt and "service_location" in prompt
    assert "What are the opening hours?" in prompt


def test_generator_says_so_when_there_is_no_amount_to_convert(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft("operaciones", {**METADATA, "budget_range": None}, ASPECTS, [])
    assert "none: the RFP gives no amount we can convert" in seen["prompt"]


def test_revision_gets_the_previous_draft_and_the_feedback(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft(
        "operaciones", METADATA, ASPECTS, [],
        previous_draft="OLD DRAFT TEXT", feedback="COMPLIANCE: fix the setup time.",
    )
    assert "OLD DRAFT TEXT" in seen["prompt"]
    assert "COMPLIANCE: fix the setup time." in seen["prompt"]


def test_first_draft_has_no_revision_section(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft("operaciones", METADATA, ASPECTS, [])
    assert "previous draft" not in seen["prompt"]


def test_code_fences_are_removed_and_empty_replies_are_refused(monkeypatch):
    capture(monkeypatch, reply="```markdown\n## Operations and Delivery\n- Text.\n```")
    draft = generator.generate_draft("operaciones", METADATA, ASPECTS, [])
    assert draft == "## Operations and Delivery\n- Text."
    capture(monkeypatch, reply="   ")
    with pytest.raises(ValueError):
        generator.generate_draft("operaciones", METADATA, ASPECTS, [])


def test_unknown_department_is_refused():
    with pytest.raises(ValueError):
        generator.generate_draft("finance", METADATA, ASPECTS, [])


# --- readability evaluator ------------------------------------------------------

EASY = "We cook the food. We serve the meal. The team is kind. " * 15
HARD = (
    "Institutional procurement considerations necessitate comprehensive "
    "multidimensional organizational coordination across geographically "
    "distributed operational environments, notwithstanding considerable "
    "administrative complexity and interdepartmental accountability. "
) * 6


def test_easy_text_passes_readability():
    result = evaluators.evaluate_readability(EASY)
    assert result["pass"] is True and result["score"] is not None
    assert result["score"] <= settings.MAX_GRADE_LEVEL


def test_hard_text_fails_readability_with_the_score_in_the_details():
    result = evaluators.evaluate_readability(HARD)
    assert result["pass"] is False
    assert result["score"] > settings.MAX_GRADE_LEVEL
    assert str(result["score"]) in result["details"]


def test_text_under_100_words_is_not_scored_and_says_so():
    result = evaluators.evaluate_readability("## Title\n- A short draft.")
    assert result["pass"] is True and result["score"] is None
    assert "could not be scored" in result["details"]


def test_markdown_bullets_are_scored_as_separate_sentences():
    bullets = "".join(f"- We cook food for guest number {i} today\n" for i in range(40))
    assert evaluators.evaluate_readability("## Heading\n" + bullets)["pass"] is True


# --- relevance evaluator ---------------------------------------------------------

def test_relevance_maps_the_numbers_back_to_the_real_aspects(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(missing=[2]))
    result = evaluators.evaluate_relevance(GOOD_DRAFT, ASPECTS)
    assert result == {"pass": False, "missing_aspects": [ASPECTS[1]]}


def test_relevance_ignores_numbers_that_are_not_real_aspects(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(missing=[0, 7, "x"]))
    assert evaluators.evaluate_relevance(GOOD_DRAFT, ASPECTS)["pass"] is True


def test_relevance_passes_when_nothing_is_missing_or_there_is_nothing_to_cover(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(missing=[]))
    assert evaluators.evaluate_relevance(GOOD_DRAFT, ASPECTS)["pass"] is True
    assert evaluators.evaluate_relevance(GOOD_DRAFT, []) == {"pass": True, "missing_aspects": []}


def test_relevance_reply_that_is_not_a_list_raises(monkeypatch):
    monkeypatch.setattr(llm, "call_generation_llm", lambda prompt, *, system=None: '{"missing": "all"}')
    with pytest.raises(llm.LlmJsonError):
        evaluators.evaluate_relevance(GOOD_DRAFT, ASPECTS)


# --- compliance evaluator ---------------------------------------------------------

def compliance(monkeypatch, draft, department="operaciones", competitors=()):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(competitors=competitors))
    return evaluators.evaluate_compliance(
        department, draft, metadata=METADATA, key_aspects=ASPECTS, open_questions=QUESTIONS)


def test_a_compliant_draft_passes(monkeypatch):
    result = compliance(monkeypatch, GOOD_DRAFT)
    assert result["pass"] is True and result["violations"] == []


def test_invented_number_is_flagged_with_the_sentence_and_the_figure(monkeypatch):
    draft = GOOD_DRAFT + "- We will serve 500 meals a day.\n"
    result = compliance(monkeypatch, draft)
    assert result["rule_ids"] == ["NO-INVENTED-NUMBERS"]
    assert "500" in result["violations"][0]["message"]
    assert "500 meals a day" in result["violations"][0]["evidence"]


def test_numbers_from_the_rfp_and_the_conversion_are_not_flagged(monkeypatch):
    draft = GOOD_DRAFT + "- The range goes up to $75,000 USD (300,000,000 COP).\n"
    assert compliance(monkeypatch, draft)["pass"] is True


def test_list_markers_are_not_mistaken_for_figures(monkeypatch):
    draft = GOOD_DRAFT.replace("- Kitchen", "1. Kitchen")
    assert compliance(monkeypatch, draft)["pass"] is True


def test_setup_promise_under_10_days_fails_with_the_rule_id(monkeypatch):
    # The CONTEXT-anchored failure case, now through the full compliance evaluator.
    draft = GOOD_DRAFT.replace("takes 10 business days", "takes 5 business days")
    result = compliance(monkeypatch, draft)
    assert result["pass"] is False
    # "5" is also a figure that is not in the RFP, so both rules fire.
    assert result["rule_ids"] == ["NO-INVENTED-NUMBERS", "SETUP-MIN-10-DAYS"]


def test_competitor_found_by_the_model_is_flagged_when_it_is_really_in_the_draft(monkeypatch):
    draft = GOOD_DRAFT + "- Unlike FireGrill Co, we use charcoal.\n"
    result = compliance(monkeypatch, draft, competitors=["FireGrill Co"])
    assert result["rule_ids"] == ["NO-COMPETITORS"]
    assert "FireGrill Co" in result["violations"][0]["evidence"]


def test_competitor_the_model_made_up_is_ignored(monkeypatch):
    assert compliance(monkeypatch, GOOD_DRAFT, competitors=["Ghost Burgers"])["pass"] is True


def test_client_and_brasaland_are_never_reported_as_competitors(monkeypatch):
    draft = GOOD_DRAFT + "- Sunset Bay Resorts and Brasaland will work together.\n"
    result = compliance(monkeypatch, draft, competitors=["Sunset Bay", "Brasaland"])
    assert result["pass"] is True


def test_marketing_draft_without_pillars_or_validity_fails(monkeypatch):
    result = compliance(monkeypatch, GOOD_DRAFT, department="marketing")
    assert result["rule_ids"] == ["BRAND-PILLARS", "OFFER-VALIDITY-30-DAYS"]


# --- all three together ---------------------------------------------------------

def run_section(monkeypatch, draft=GOOD_DRAFT, **fake_options):
    monkeypatch.setattr(llm, "call_generation_llm", fake_model(draft=draft, **fake_options))
    return evaluators.evaluate_section(
        "operaciones", draft, metadata=METADATA, key_aspects=ASPECTS, open_questions=QUESTIONS)


def test_section_that_passes_everything_has_overall_pass_and_no_feedback(monkeypatch):
    result = run_section(monkeypatch)
    assert result["overall_pass"] is True
    assert result["feedback_for_generator"] == ""
    assert set(result) == {
        "department_id", "readability", "relevance", "compliance",
        "overall_pass", "feedback_for_generator",
    }


def test_one_failing_evaluator_fails_the_section_with_concrete_feedback(monkeypatch):
    # Evaluation fails (the ticket asks for this case): relevance says aspect 2 is missing.
    result = run_section(monkeypatch, missing=[2])
    assert result["overall_pass"] is False
    assert result["relevance"]["pass"] is False
    assert result["readability"]["pass"] is True and result["compliance"]["pass"] is True
    assert ASPECTS[1] in result["feedback_for_generator"]


def test_the_three_evaluators_really_run_at_the_same_time(monkeypatch):
    # Both model-based evaluators wait for each other. One after the other
    # they would time out, so this only passes if they run in parallel.
    barrier = threading.Barrier(2, timeout=5)

    def _fake(prompt, *, system=None):
        barrier.wait()
        if "relevance checker" in system:
            return json.dumps({"missing": []})
        return json.dumps({"competitors": []})

    monkeypatch.setattr(llm, "call_generation_llm", _fake)
    result = evaluators.evaluate_section(
        "operaciones", GOOD_DRAFT, metadata=METADATA, key_aspects=ASPECTS, open_questions=QUESTIONS)
    assert result["overall_pass"] is True


# --- fixes found in the first live run -------------------------------------------

def test_the_reference_rate_sentence_is_not_flagged_as_an_invented_number(monkeypatch):
    draft = GOOD_DRAFT + "- The reference rate is 1 USD = 4,000 COP, to be confirmed.\n"
    assert compliance(monkeypatch, draft)["pass"] is True


def test_a_different_rate_is_still_flagged(monkeypatch):
    draft = GOOD_DRAFT + "- The reference rate is 1 USD = 3,900 COP, to be confirmed.\n"
    result = compliance(monkeypatch, draft)
    assert result["rule_ids"] == ["NO-INVENTED-NUMBERS"]
    assert "3,900" in result["violations"][0]["message"]


def test_relevance_checker_is_told_contact_and_deadline_are_background():
    assert "contact person" in evaluators.RELEVANCE_SYSTEM
    assert "proposal deadline" in evaluators.RELEVANCE_SYSTEM


def test_procurement_is_told_not_to_state_supplier_lead_times_on_its_own(monkeypatch):
    seen = capture(monkeypatch)
    generator.generate_draft("procurement", METADATA, ASPECTS, [])
    assert "unless the facts give them" in seen["system"]
