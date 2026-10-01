"""
tests/pipelines/test_rfp_approval_logic.py -- the plain-code parts of Part 3
(data/pipelines/rfp_approval/): validating a human's answer, finding the
CONTEXT section 7 conflicts from structured data, and building the final
document. No model, no database, no graph.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_approval import conflicts, decisions, final_document, settings  # noqa: E402

# --- the settings match CONTEXT-brasaland.md ----------------------------------

def test_the_approvers_and_arbiters_are_the_people_named_in_context():
    assert settings.APPROVERS == {
        "marketing": "Camila Ospina", "operaciones": "Felipe Guerrero",
        "procurement": "Lucia Fernandez", "training": "Jake Morrison", "ceo": "Mariana Restrepo",
    }
    assert settings.ARBITERS == {
        "cost-vs-feasibility": "Camila Ospina",
        "setup-sla-breach": "Felipe Guerrero",
        "ceo-threshold": "Mariana Restrepo",
    }
    assert settings.ESCALATION_ARBITER == {"setup-sla-breach": "Camila Ospina"}
    assert settings.CEO_APPROVAL_THRESHOLD_USD == 50_000


# --- validating a human's answer ------------------------------------------------

def test_a_plain_approval_is_accepted_and_cleaned():
    assert decisions.validate_decision("marketing", {"action": "approve"}) == {
        "action": "approve", "comments": "", "estimates": {}}
    assert decisions.validate_decision("marketing", {"action": "approve", "comments": "  Looks right.  "})["comments"] == "Looks right."


@pytest.mark.parametrize("action", ["reject", "request_changes"])
def test_rejecting_or_asking_for_changes_needs_a_reason(action):
    with pytest.raises(decisions.InvalidDecision, match="Say why"):
        decisions.validate_decision("training", {"action": action})
    with pytest.raises(decisions.InvalidDecision, match="Say why"):
        decisions.validate_decision("training", {"action": action, "comments": "no"})
    ok = decisions.validate_decision("training", {"action": action, "comments": "The certification time is missing."})
    assert ok["action"] == action


@pytest.mark.parametrize("bad", [
    None, "approve", ["approve"], {}, {"action": "approved"}, {"action": "APPROVE"}, {"action": None},
])
def test_anything_that_is_not_one_of_the_three_actions_is_refused(bad):
    with pytest.raises(decisions.InvalidDecision):
        decisions.validate_decision("marketing", bad)


def test_unknown_fields_are_refused_so_typos_do_not_pass_silently():
    with pytest.raises(decisions.InvalidDecision, match="Unknown field"):
        decisions.validate_decision("marketing", {"action": "approve", "comment": "typo"})


def test_only_real_approvers_are_accepted():
    with pytest.raises(decisions.InvalidDecision, match="not an approver"):
        decisions.validate_decision("finance", {"action": "approve"})


def test_the_ceo_can_approve_or_reject_but_not_ask_for_changes():
    assert decisions.validate_decision("ceo", {"action": "approve"})["action"] == "approve"
    assert decisions.validate_decision("ceo", {"action": "reject", "comments": "Margin is too thin."})["action"] == "reject"
    with pytest.raises(decisions.InvalidDecision):
        decisions.validate_decision("ceo", {"action": "request_changes", "comments": "Change the pricing please."})


def test_estimates_are_only_accepted_from_the_two_owners_who_enter_them():
    ok = decisions.validate_decision(
        "procurement", {"action": "approve", "estimates": {"ingredient_cost_per_cover_usd": 4}})
    assert ok["estimates"] == {"ingredient_cost_per_cover_usd": 4.0}
    ok = decisions.validate_decision("operaciones", {"action": "approve", "estimates": {"price_per_cover_usd": 12.5}})
    assert ok["estimates"] == {"price_per_cover_usd": 12.5}
    with pytest.raises(decisions.InvalidDecision, match="not accepted from 'training'"):
        decisions.validate_decision("training", {"action": "approve", "estimates": {"price_per_cover_usd": 1}})
    with pytest.raises(decisions.InvalidDecision, match="can only give"):
        decisions.validate_decision("procurement", {"action": "approve", "estimates": {"price_per_cover_usd": 1}})


@pytest.mark.parametrize("value", [0, -3, float("nan"), float("inf"), "12", True, None])
def test_estimates_must_be_real_positive_numbers(value):
    with pytest.raises(decisions.InvalidDecision):
        decisions.validate_decision("operaciones", {"action": "approve", "estimates": {"price_per_cover_usd": value}})


def test_estimates_only_come_with_an_approval():
    with pytest.raises(decisions.InvalidDecision, match="only be given together with 'approve'"):
        decisions.validate_decision("operaciones", {
            "action": "request_changes", "comments": "Please redo the staffing plan.",
            "estimates": {"price_per_cover_usd": 12}})


def test_the_arbiters_cost_decision_is_checked_too():
    ok = decisions.validate_arbitration("cost-vs-feasibility", {"choice": "raise_price", "comments": "Margins need it."})
    assert ok == {"choice": "raise_price", "comments": "Margins need it."}
    with pytest.raises(decisions.InvalidDecision):
        decisions.validate_arbitration("cost-vs-feasibility", {"choice": "ignore", "comments": "Margins need it."})
    with pytest.raises(decisions.InvalidDecision, match="settled by its rule"):
        decisions.validate_arbitration("setup-sla-breach", {"choice": "raise_price", "comments": "Margins need it."})


# --- the RFP's yearly value and the CEO rule ---------------------------------------

@pytest.mark.parametrize("budget, expected", [
    ("$60,000\u2013$75,000 USD", {"low": 60000, "high": 75000}),
    ("50.000.000 COP al a\u00f1o", {"low": 12500.0, "high": 12500.0}),
    ("$60,000 USD (240,000,000 COP)", {"low": 60000, "high": 60000}),
    ("$60,000", None),   # currency unclear: never guess
    ("", None),
    (None, None),
])
def test_the_yearly_value_is_read_from_the_budget_without_guessing_a_currency(budget, expected):
    assert conflicts.estimated_annual_value_usd({"budget_range": budget}) == expected


@pytest.mark.parametrize("budget, needed", [
    ("$60,000\u2013$75,000 USD", True),    # Sunset Bay in CONTEXT section 4
    ("$50,000 USD", False),                # "above" means strictly above
    ("$50,001 USD", True),
    ("$30,000\u2013$55,000 USD", True),    # a range counts by its high end
    (None, False),                          # Andes Tech: no budget, no CEO step
])
def test_the_ceo_is_needed_above_50000_usd_a_year(budget, needed):
    assert conflicts.ceo_required({"budget_range": budget}) is needed


# --- conflict triggers --------------------------------------------------------------

SUNSET = {"budget_range": "$60,000\u2013$75,000 USD"}
CLEAN = "- Setup and launch take at least 10 business days."
BAD = "- Kitchen setup takes 5 business days after signing."


def section(text=CLEAN, status="approved", **estimates):
    return {"draft_content": text, "status": status, "estimates": estimates}


def triggers(result):
    return [c["trigger"] for c in result["conflicts"]]


def test_clean_drafts_with_the_ceo_approved_have_no_conflicts():
    result = conflicts.detect_conflicts(SUNSET, {"marketing": section(), "operaciones": section()}, "approved")
    assert result == {"conflicts": [], "warnings": []}


def test_ceo_threshold_fires_until_the_ceo_approves():
    for status in ("pending", "rejected"):
        result = conflicts.detect_conflicts(SUNSET, {"marketing": section()}, status)
        conflict = result["conflicts"][0]
        assert conflict["trigger"] == "ceo-threshold" and conflict["arbiter"] == "Mariana Restrepo"
        assert conflict["details"]["ceo_status"] == status
        assert conflict["forced_action"] is None
    assert "ceo-threshold" not in triggers(conflicts.detect_conflicts(SUNSET, {"marketing": section()}, "approved"))


def test_no_budget_means_no_ceo_conflict():
    assert conflicts.detect_conflicts({"budget_range": None}, {"marketing": section()}) == {"conflicts": [], "warnings": []}


def test_a_budget_with_an_unclear_currency_is_flagged_as_a_warning_not_guessed():
    result = conflicts.detect_conflicts({"budget_range": "$60,000"}, {"marketing": section()})
    assert result["conflicts"] == []
    assert "currency is unclear" in result["warnings"][0]


def test_setup_breach_in_operations_is_felipes_to_reject_without_escalation():
    result = conflicts.detect_conflicts({}, {"operaciones": section(BAD), "marketing": section()})
    conflict = result["conflicts"][0]
    assert conflict["trigger"] == "setup-sla-breach"
    assert conflict["arbiter"] == "Felipe Guerrero" and conflict["escalated_to"] is None
    assert conflict["sections"] == ["operaciones"]
    assert conflict["forced_action"] == "request_changes"
    assert "5 business days" in conflict["details"]["evidence"]["operaciones"][0]


def test_setup_breach_embedded_by_other_departments_escalates_to_camila():
    result = conflicts.detect_conflicts({}, {"operaciones": section(BAD), "training": section(BAD), "marketing": section()})
    conflict = result["conflicts"][0]
    assert conflict["escalated_to"] == "Camila Ospina"
    assert conflict["sections"] == ["operaciones", "training"]


def test_ten_or_more_business_days_is_not_a_breach():
    assert conflicts.detect_conflicts({}, {"operaciones": section("- Setup takes 12 business days.")})["conflicts"] == []


def test_cost_vs_feasibility_fires_when_ingredients_cost_more_than_the_price():
    sections = {
        "procurement": section(ingredient_cost_per_cover_usd=12.0),
        "operaciones": section(price_per_cover_usd=10.0),
    }
    conflict = conflicts.detect_conflicts({}, sections)["conflicts"][0]
    assert conflict["trigger"] == "cost-vs-feasibility" and conflict["arbiter"] == "Camila Ospina"
    assert conflict["sections"] == ["operaciones", "procurement"]
    assert conflict["details"]["ingredient_cost_per_cover_usd"] == 12.0
    assert conflict["forced_action"] == "request_changes"


def test_cost_vs_feasibility_stays_quiet_when_the_price_covers_the_cost_or_a_number_is_missing():
    cheap = {"procurement": section(ingredient_cost_per_cover_usd=4.0), "operaciones": section(price_per_cover_usd=10.0)}
    assert conflicts.detect_conflicts({}, cheap)["conflicts"] == []
    equal = {"procurement": section(ingredient_cost_per_cover_usd=10.0), "operaciones": section(price_per_cover_usd=10.0)}
    assert conflicts.detect_conflicts({}, equal)["conflicts"] == []
    assert conflicts.detect_conflicts({}, {"procurement": section(ingredient_cost_per_cover_usd=99.0)})["conflicts"] == []


def test_an_estimate_only_counts_once_its_owner_has_approved():
    sections = {
        "procurement": section(status="pending", ingredient_cost_per_cover_usd=12.0),
        "operaciones": section(price_per_cover_usd=10.0),
    }
    assert conflicts.detect_conflicts({}, sections)["conflicts"] == []


def test_several_conflicts_can_be_open_at_once():
    sections = {
        "operaciones": section(BAD, price_per_cover_usd=10.0),
        "procurement": section(ingredient_cost_per_cover_usd=12.0),
    }
    found = triggers(conflicts.detect_conflicts(SUNSET, sections, "pending"))
    assert sorted(found) == ["ceo-threshold", "cost-vs-feasibility", "setup-sla-breach"]


# --- the final document ----------------------------------------------------------------

NOW = datetime(2026, 10, 1, 12, 0, 0)


def approval(status="approved", acted_by="manager@brasaland.test"):
    return {"status": status, "acted_by": acted_by, "decided_at": "2026-10-01T10:00:00", "comments": ""}


def approvals(*subjects, status="approved"):
    return {subject: approval(status) for subject in subjects}


DRAFTS = {
    "marketing": {"draft_content": "## Brand and Commercial Terms\n- Offer valid for 30 days from issuance."},
    "operaciones": {"draft_content": "- Setup takes at least 10 business days."},
}


def test_the_final_document_has_every_approved_section_in_a_fixed_order_with_its_approver():
    document = final_document.build_final_document(
        7, {"client_name": "Sunset Bay Resorts, LLC", "rfp_id": "SBR-1", **SUNSET},
        {"operaciones": DRAFTS["operaciones"], "marketing": DRAFTS["marketing"]},
        approvals("marketing", "operaciones", "ceo"), [], now=NOW)
    assert document["ticket_id"] == 7 and document["generated_at"] == "2026-10-01T12:00:00"
    assert [s["department_id"] for s in document["sections"]] == ["marketing", "operaciones"]
    assert document["sections"][0]["approver"] == "Camila Ospina"
    assert [a["subject"] for a in document["approvals"]] == ["marketing", "operaciones", "ceo"]
    value = document["total_estimated_value"]
    assert (value["usd_low"], value["usd_high"], value["cop_high"]) == (60000, 75000, 300_000_000)


def test_markdown_shows_the_value_in_both_currencies_every_section_and_the_approvals():
    document = final_document.build_final_document(
        7, {"client_name": "Sunset Bay Resorts, LLC", **SUNSET}, DRAFTS, approvals("marketing", "operaciones", "ceo"), [], now=NOW)
    text = final_document.render_markdown(document)
    assert text.startswith("# Proposal for Sunset Bay Resorts, LLC")
    assert "$60,000\u2013$75,000 USD (240,000,000\u2013300,000,000 COP" in text
    assert "## Brand and Commercial Terms" in text
    assert "## Operations and Delivery" in text      # added because that draft had no heading of its own
    assert "| Mariana Restrepo | CEO |" in text and "| Felipe Guerrero | operaciones |" in text


def test_no_budget_means_no_value_is_invented_and_no_ceo_row():
    document = final_document.build_final_document(
        7, {"client_name": "Andes Tech Solutions"}, DRAFTS, approvals("marketing", "operaciones"), [], now=NOW)
    assert document["total_estimated_value"] is None
    assert [a["subject"] for a in document["approvals"]] == ["marketing", "operaciones"]
    assert "not stated in the RFP" in final_document.render_markdown(document)


def test_it_refuses_to_build_until_every_department_has_approved_and_says_who_is_missing():
    with pytest.raises(final_document.NotReady) as error:
        final_document.build_final_document(
            7, {}, DRAFTS, {"marketing": approval(), "operaciones": approval("rejected")}, [], now=NOW)
    assert error.value.blockers == ["operaciones: Felipe Guerrero has not approved (status: rejected)"]


def test_it_refuses_to_build_without_the_ceo_when_the_value_is_above_the_threshold():
    with pytest.raises(final_document.NotReady) as error:
        final_document.build_final_document(7, SUNSET, DRAFTS, approvals("marketing", "operaciones"), [], now=NOW)
    assert error.value.blockers == ["ceo: Mariana Restrepo has not approved (status: pending)"]


def test_it_refuses_to_build_while_a_conflict_is_open():
    open_conflicts = conflicts.detect_conflicts({}, {"operaciones": section(BAD)})["conflicts"]
    with pytest.raises(final_document.NotReady) as error:
        final_document.build_final_document(7, {}, DRAFTS, approvals("marketing", "operaciones"), open_conflicts, now=NOW)
    assert error.value.blockers == ["open conflict: setup-sla-breach (arbiter: Felipe Guerrero)"]


def test_a_missing_approval_row_counts_as_pending():
    with pytest.raises(final_document.NotReady) as error:
        final_document.build_final_document(7, {}, DRAFTS, {}, [], now=NOW)
    assert len(error.value.blockers) == 2 and all("pending" in b for b in error.value.blockers)
