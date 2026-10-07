"""
conflicts.py -- finds the conflicts CONTEXT-brasaland.md section 7 names, from
STRUCTURED data only (Milestone 9, Part 3).

Nothing here reads free text for meaning, and nothing here is a model. Each
trigger is a plain check on a field that is saved in the ticket:

  setup-sla-breach     the draft text fails the code check for "setup or delivery
                       in fewer than 10 business days" (the same check Part 2 uses)
  cost-vs-feasibility  two numbers the approvers entered: the ingredient cost per
                       cover (procurement) against the price per cover (operaciones)
  ceo-threshold        the estimated yearly value parsed from the RFP's budget,
                       above $50,000 USD, while the CEO has not approved yet

detect_conflicts() only FINDS them. Who settles each one, and how, is written
in each conflict (the fixed arbiter from CONTEXT) and carried out by the
arbitration node in the graph. Agents may surface a conflict; they never
resolve it by consensus.
"""

import re

from rfp_response import facts, rules
from rfp_response import settings as response_settings

from . import settings


def estimated_annual_value_usd(metadata: dict):
    """The RFP's stated yearly value as {"low", "high"} in USD, or None.

    None when the RFP states no amount, or when the currency can't be told
    (a bare "$60,000"): we never guess a currency.
    """
    budget = (metadata or {}).get("budget_range")
    if not budget:
        return None
    has_usd = bool(re.search(r"\bUSD\b|US\$|d[oó]lares", budget, re.IGNORECASE))
    has_cop = bool(re.search(r"\bCOP\b|COL\$|pesos", budget, re.IGNORECASE))

    if has_usd and has_cop:
        # Both currencies are written: use the amounts that are written in dollars.
        pieces = re.findall(r"(?:US\$|\$)\s*(\d[\d.,]*)|(\d[\d.,]*)\s*USD", budget, re.IGNORECASE)
        amounts = [facts._to_number(first or second) for first, second in pieces]
    elif has_usd:
        amounts = [facts._to_number(raw) for raw in re.findall(r"\d[\d.,]*", budget)]
    elif has_cop:
        rate = response_settings.COP_PER_USD
        amounts = [facts._to_number(raw) for raw in re.findall(r"\d[\d.,]*", budget)]
        amounts = [amount / rate for amount in amounts if amount is not None]
    else:
        return None

    amounts = [amount for amount in amounts if amount is not None]
    if not amounts:
        return None
    return {"low": min(amounts), "high": max(amounts)}


def ceo_required(metadata: dict) -> bool:
    """CONTEXT section 5: contracts ABOVE $50,000 USD a year need the CEO.
    A range counts by its high end, so $60,000-$75,000 needs the CEO."""
    value = estimated_annual_value_usd(metadata)
    return value is not None and value["high"] > settings.CEO_APPROVAL_THRESHOLD_USD


def _approved_estimate(sections: dict, department_id: str):
    section = sections.get(department_id) or {}
    if section.get("status") != settings.APPROVED:
        return None  # an estimate only counts once its owner has approved
    return (section.get("estimates") or {}).get(settings.ESTIMATE_FIELDS[department_id])


def detect_conflicts(metadata: dict, sections: dict, ceo_status: str = settings.PENDING) -> dict:
    """Return {"conflicts": [...], "warnings": [...]}.

    sections: department_id -> {"draft_content": str, "status": "pending" |
    "approved" | "rejected", "estimates": {field: number}}
    ceo_status: "pending" | "approved" | "rejected"
    """
    conflicts, warnings = [], []

    # --- setup-sla-breach: any section promising setup or delivery under 10 business days
    breaches = {}
    for department_id, section in sections.items():
        violations = rules.check_setup_time(section.get("draft_content") or "")
        if violations:
            breaches[department_id] = [v["evidence"] for v in violations]
    if breaches:
        others_embed_it = any(department_id != "operaciones" for department_id in breaches)
        conflicts.append({
            "trigger": settings.TRIGGER_SETUP,
            "arbiter": settings.ARBITERS[settings.TRIGGER_SETUP],
            "escalated_to": settings.ESCALATION_ARBITER[settings.TRIGGER_SETUP] if others_embed_it else None,
            "sections": sorted(breaches),
            "details": {"evidence": breaches, "minimum_business_days": response_settings.MIN_SETUP_BUSINESS_DAYS},
            "resolution": (
                f"Force request_changes on every section that promises less than "
                f"{response_settings.MIN_SETUP_BUSINESS_DAYS} business days, until all of them promise at least that."
            ),
            "forced_action": settings.REQUEST_CHANGES,
        })

    # --- cost-vs-feasibility: ingredient cost per cover against price per cover
    cost = _approved_estimate(sections, "procurement")
    price = _approved_estimate(sections, "operaciones")
    if cost is not None and price is not None and cost > price * settings.MAX_INGREDIENT_COST_SHARE:
        conflicts.append({
            "trigger": settings.TRIGGER_COST,
            "arbiter": settings.ARBITERS[settings.TRIGGER_COST],
            "escalated_to": None,
            "sections": ["operaciones", "procurement"],
            "details": {
                "ingredient_cost_per_cover_usd": cost,
                "price_per_cover_usd": price,
                "maximum_cost_share": settings.MAX_INGREDIENT_COST_SHARE,
            },
            "resolution": "Raise the price or reduce the scope; force request_changes on both sections.",
            "forced_action": settings.REQUEST_CHANGES,
        })

    # --- ceo-threshold: above $50,000 a year, and the CEO has not approved
    value = estimated_annual_value_usd(metadata)
    if value is None and (metadata or {}).get("budget_range"):
        warnings.append(
            "The RFP states a budget but its currency is unclear, so the CEO threshold could not be checked."
        )
    if value is not None and value["high"] > settings.CEO_APPROVAL_THRESHOLD_USD and ceo_status != settings.APPROVED:
        conflicts.append({
            "trigger": settings.TRIGGER_CEO,
            "arbiter": settings.ARBITERS[settings.TRIGGER_CEO],
            "escalated_to": None,
            "sections": [],
            "details": {
                "estimated_value_usd": value,
                "threshold_usd": settings.CEO_APPROVAL_THRESHOLD_USD,
                "ceo_status": ceo_status,
            },
            "resolution": (
                "Block the final document until the CEO approves. "
                "If the CEO rejects, the ticket goes back to needs_human_review."
            ),
            "forced_action": None,
        })

    return {"conflicts": conflicts, "warnings": warnings}
