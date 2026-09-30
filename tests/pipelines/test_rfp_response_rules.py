"""
tests/pipelines/test_rfp_response_rules.py -- tests for the compliance rules
(data/pipelines/rfp_response/rules.py) and the EvaluationResult builder
(data/pipelines/rfp_response/evaluation.py).

No model is involved: these rules are plain code checks.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_response import evaluation, rules, settings  # noqa: E402


# --- every price in both currencies -------------------------------------------

def test_price_in_both_currencies_passes():
    text = "The contract is worth $60,000 USD (about 240,000,000 COP) per year."
    assert rules.check_price_dual_currency(text) == []


def test_price_in_usd_only_fails_and_asks_for_cop():
    violations = rules.check_price_dual_currency("The contract is worth $60,000 USD per year.")
    assert [v["rule_id"] for v in violations] == ["PRICE-DUAL-CURRENCY"]
    assert "COP" in violations[0]["message"]
    assert "$60,000 USD" in violations[0]["evidence"]


def test_price_in_cop_only_fails_and_asks_for_usd():
    violations = rules.check_price_dual_currency("Each lunch costs 25,000 COP.")
    assert len(violations) == 1 and "USD" in violations[0]["message"]


def test_sentences_without_prices_are_ignored():
    assert rules.check_price_dual_currency("Service runs on Tuesdays and Thursdays for 220 people.") == []


# --- brand pillars (marketing only) ----------------------------------------------

def test_all_three_pillars_pass():
    text = "We promise consistent quality, a warm experience and speed of service."
    assert rules.check_brand_pillars(text.replace("a warm experience", "warm experience")) == []


def test_missing_pillar_is_named():
    violations = rules.check_brand_pillars("We promise consistent quality and warm experience.")
    assert len(violations) == 1
    assert "speed of service" in violations[0]["message"]


# --- setup and delivery times --------------------------------------------------

@pytest.mark.parametrize("sentence, should_fail", [
    ("Setup will take 5 business days.", True),
    ("Setup takes 48 hours after signing.", True),
    ("Service can start same day.", True),
    ("Setup takes 1 week.", True),
    ("Setup takes 10 business days.", False),
    ("Launch in 2 weeks.", False),
    ("We deliver on 2 days a week.", False),
    ("Offer valid 30 days from issuance; setup takes 12 business days.", False),
])
def test_setup_time_rule(sentence, should_fail):
    violations = rules.check_setup_time(sentence)
    assert bool(violations) is should_fail
    if should_fail:
        assert violations[0]["rule_id"] == "SETUP-MIN-10-DAYS"


def test_draft_promising_setup_under_10_days_fails_compliance():
    # The CONTEXT-anchored failure case (CONTEXT section 5: no setup or
    # delivery promise shorter than 10 business days).
    draft = "Operations will complete kitchen setup and launch in 5 business days."
    result = rules.check_compliance("operaciones", draft)
    assert result["pass"] is False
    assert result["rule_ids"] == ["SETUP-MIN-10-DAYS"]
    assert "5 business days" in result["violations"][0]["evidence"]


# --- which rules apply to which department --------------------------------------

def test_marketing_only_rules_are_not_applied_to_other_departments():
    draft = "Operations runs the kitchen on Tuesdays and Thursdays."
    assert rules.check_compliance("operaciones", draft)["pass"] is True
    marketing = rules.check_compliance("marketing", draft)
    assert marketing["rule_ids"] == ["BRAND-PILLARS", "OFFER-VALIDITY-30-DAYS"]


# --- offer validity (marketing only) ----------------------------------------------

def test_offer_validity_written_with_words_and_digits_passes():
    assert rules.check_offer_validity("This offer is valid for thirty (30) days from issuance.") == []


def test_missing_offer_validity_fails():
    violations = rules.check_offer_validity("We look forward to working with you.")
    assert [v["rule_id"] for v in violations] == ["OFFER-VALIDITY-30-DAYS"]


# --- competitors ---------------------------------------------------------------

def test_competitor_names_are_checked_when_a_list_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "COMPETITOR_NAMES", ("AcmeGrill",))
    violations = rules.check_no_competitors("Unlike AcmeGrill, we grill over charcoal.")
    assert [v["rule_id"] for v in violations] == ["NO-COMPETITORS"]


def test_no_competitor_check_when_no_list_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "COMPETITOR_NAMES", ())
    assert rules.check_no_competitors("Unlike AcmeGrill, we grill over charcoal.") == []


# --- the EvaluationResult -----------------------------------------------------

READABLE = {"pass": True, "score": 9.0, "details": "Grade level 9.0."}
RELEVANT = {"pass": True, "missing_aspects": []}


def test_result_passes_when_all_three_evaluators_pass():
    compliance = rules.check_compliance("operaciones", "Setup takes 12 business days.")
    result = evaluation.combine("operaciones", READABLE, RELEVANT, compliance)
    assert result["overall_pass"] is True
    assert result["feedback_for_generator"] == ""
    assert result["department_id"] == "operaciones"


def test_result_fails_when_any_one_fails_and_feedback_is_concrete():
    compliance = rules.check_compliance("operaciones", "Setup takes 3 business days.")
    result = evaluation.combine("operaciones", READABLE, RELEVANT, compliance)
    assert result["overall_pass"] is False
    assert "SETUP-MIN-10-DAYS" in result["feedback_for_generator"]
    assert "Setup takes 3 business days." in result["feedback_for_generator"]


def test_feedback_lists_each_missing_aspect():
    relevance = {"pass": False, "missing_aspects": ["Peak season staffing", "Deadline"]}
    compliance = {"pass": True, "rule_ids": [], "violations": []}
    result = evaluation.combine("operaciones", READABLE, relevance, compliance)
    assert result["overall_pass"] is False
    assert "Peak season staffing" in result["feedback_for_generator"]
    assert "Deadline" in result["feedback_for_generator"]


# --- a price counts as shown in both currencies within one bullet or paragraph ---

def test_price_in_two_sentences_of_the_same_bullet_passes():
    text = "- The contract value is $60,000 USD. In local currency that is 240,000,000 COP."
    assert rules.check_price_dual_currency(text) == []


def test_price_split_across_two_bullets_still_fails():
    text = "- The contract value is $60,000 USD.\n- In local currency that is 240,000,000 COP."
    violations = rules.check_price_dual_currency(text)
    assert [v["rule_id"] for v in violations] == ["PRICE-DUAL-CURRENCY", "PRICE-DUAL-CURRENCY"]
