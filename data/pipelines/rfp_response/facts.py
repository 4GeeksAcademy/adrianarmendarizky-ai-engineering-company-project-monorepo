"""
facts.py -- the facts a proposal draft is allowed to use (Milestone 9, Part 2).

Generators and evaluators both read from here, so they agree on what counts
as a known fact:
  shared_details()    the RFP details every department sees
  currency_figures()  COP/USD equivalents worked out here in CODE from the
                      RFP's own amount. The model never converts anything.
  allowed_numbers()   every number a draft may contain
"""

import re

from rfp_intake.workers import _numbers

from . import settings

# The RFP details passed to every generator (same ones Part 1 extracted).
SHARED_FIELDS = (
    "rfp_id", "client_name", "location", "service_type", "scope", "deadline", "budget_range",
)
# Renamed so the model can't misread them (same fix as Part 1's workers):
# the deadline is for the PROPOSAL, and the location is where the service is.
RENAMES = {"deadline": "proposal_deadline", "location": "service_location"}


def shared_details(metadata: dict) -> dict:
    details = {}
    for field in SHARED_FIELDS:
        value = metadata.get(field)
        if value:
            details[RENAMES.get(field, field)] = value
    return details


def _to_number(text: str):
    """'60,000' -> 60000, '50.000.000' -> 50000000, '1,500.50' -> 1500.5."""
    text = text.strip().rstrip(".,")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        return int(re.sub(r"[.,]", "", text))
    if re.fullmatch(r"\d+", text):
        return int(text)
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def currency_figures(metadata: dict) -> list[str]:
    """Equivalents for the RFP's budget, in the other currency.

    Only when the RFP says which currency its amount is in. If it says
    neither, or already gives both, nothing is converted: we never guess.
    """
    budget = metadata.get("budget_range")
    if not budget:
        return []
    has_usd = bool(re.search(r"\bUSD\b|US\$|d[oó]lares", budget, re.IGNORECASE))
    has_cop = bool(re.search(r"\bCOP\b|COL\$|pesos", budget, re.IGNORECASE))
    if has_usd == has_cop:
        return []

    rate = settings.COP_PER_USD
    figures = []
    for raw in re.findall(r"\d[\d.,]*", budget):
        amount = _to_number(raw)
        if amount is None:
            continue
        if has_usd:
            figures.append(f"${amount:,.0f} USD = {amount * rate:,.0f} COP")
        else:
            figures.append(f"{amount:,.0f} COP = ${amount / rate:,.0f} USD")
    return figures


def allowed_numbers(metadata: dict, key_aspects: list[str], open_questions: list[str]) -> set[str]:
    """Every number (digits only) that a draft for this department may contain."""
    parts = [str(value) for value in shared_details(metadata).values()]
    parts += key_aspects + open_questions + currency_figures(metadata)
    parts.append(f"{settings.COP_PER_USD:,.0f}")  # the reference rate itself
    allowed = _numbers(" ".join(parts))
    # The two numbers the CONTEXT guidelines themselves require.
    allowed |= {str(settings.MIN_SETUP_BUSINESS_DAYS), str(settings.OFFER_VALIDITY_DAYS)}
    return allowed
