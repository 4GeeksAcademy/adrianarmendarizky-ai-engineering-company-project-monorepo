"""
rules.py -- the CONTEXT-brasaland.md section 5 guidelines, as checks that
code can run on a draft.

Each rule has an id, its plain-English text, which departments it applies to,
and a check function. A check returns a list of violations:
    {"rule_id": ..., "message": ..., "evidence": the sentence that broke it}

The pillars and offer-validity rules apply to the marketing section only,
because Marketing owns brand terms and the offer validity period
(CONTEXT section 2.1). The other rules apply to every section.

CONTEXT section 5's CEO-approval rule (contracts above $50,000 USD a year) is
about approvals, not draft content, so it belongs to Part 3.
"""

import re

from . import settings

ALL = "all"
MARKETING_ONLY = ("marketing",)

RULE_PRICE = "PRICE-DUAL-CURRENCY"
RULE_PILLARS = "BRAND-PILLARS"
RULE_SETUP = "SETUP-MIN-10-DAYS"
RULE_COMPETITORS = "NO-COMPETITORS"
RULE_VALIDITY = "OFFER-VALIDITY-30-DAYS"


def _violation(rule_id: str, message: str, evidence: str = "") -> dict:
    return {"rule_id": rule_id, "message": message, "evidence": evidence}


def _sentences(text: str) -> list[str]:
    """Split into sentences and lines (bullets, table rows)."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


# --- Every price is shown in both COP and USD ---------------------------------

USD_MARK = re.compile(r"\bUSD\b|US\$|\$\s*\d", re.IGNORECASE)
COP_MARK = re.compile(r"\bCOP\b|COL\$", re.IGNORECASE)


def check_price_dual_currency(text: str) -> list[dict]:
    # One bullet or paragraph counts as one place: "$60,000 USD. That is
    # 240,000,000 COP." is fine, because both currencies are shown together.
    found = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        has_usd = bool(USD_MARK.search(line))
        has_cop = bool(COP_MARK.search(line))
        if re.search(r"\d", line) and (has_usd or has_cop) and not (has_usd and has_cop):
            shown, missing = ("USD", "COP") if has_usd else ("COP", "USD")
            found.append(_violation(
                RULE_PRICE,
                f"This price is shown in {shown} only. Give it in {missing} as well, in the same bullet or paragraph.",
                line,
            ))
    return found


# --- The three brand pillars ------------------------------------------------

def check_brand_pillars(text: str) -> list[dict]:
    lowered = (text or "").lower()
    missing = [pillar for pillar in settings.BRAND_PILLARS if pillar not in lowered]
    if not missing:
        return []
    return [_violation(RULE_PILLARS, "Missing brand pillar(s): " + ", ".join(missing) + ".")]


# --- Setup and delivery times: at least 10 business days ---------------------

SETUP_WORDS = re.compile(
    r"\b(set[- ]?up|deliver\w*|launch\w*|go[- ]live|start\w*|begin\w*|ready|"
    r"operational|open\w*|implement\w*|install\w*|onboard\w*)\b",
    re.IGNORECASE,
)
DURATION = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*"
    r"(?:business\s+|working\s+|calendar\s+)?(hours?|days?|weeks?)\b"
    r"(?!\s*(?:a|per|each|every)\s+(?:week|month|year)|\s*/\s*(?:week|month))",
    re.IGNORECASE,
)
IMMEDIATE = re.compile(r"\b(same[- ]day|next[- ]day|overnight|immediate(?:ly)?|right away)\b", re.IGNORECASE)
# "valid for 30 days" is the offer validity period, not a setup time.
VALIDITY_PHRASE = re.compile(
    r"valid(?:ity)?[^.;]{0,40}?\d+\s*(?:calendar\s+)?days?|"
    r"\d+\s*(?:calendar\s+)?days?\s+(?:of validity|from (?:the )?(?:date of )?issuance)",
    re.IGNORECASE,
)


def _duration_in_business_days(match: re.Match) -> float:
    number = float(match.group(1))  # for a range like "5-7 days", the lower number
    unit = match.group(3).lower()
    if unit.startswith("hour"):
        return number / 24
    if unit.startswith("week"):
        return number * 5
    return number


def check_setup_time(text: str) -> list[dict]:
    found = []
    for sentence in _sentences(text):
        if not SETUP_WORDS.search(sentence):
            continue
        cleaned = VALIDITY_PHRASE.sub("", sentence)
        days = [_duration_in_business_days(m) for m in DURATION.finditer(cleaned)]
        if IMMEDIATE.search(cleaned):
            days.append(0.0)
        if days and min(days) < settings.MIN_SETUP_BUSINESS_DAYS:
            found.append(_violation(
                RULE_SETUP,
                f"This promises setup or delivery in about {min(days):g} business days. "
                f"Brasaland needs at least {settings.MIN_SETUP_BUSINESS_DAYS} business days, "
                f"so promise {settings.MIN_SETUP_BUSINESS_DAYS} or more.",
                sentence,
            ))
    return found


# --- No competitor names -------------------------------------------------

def check_no_competitors(text: str) -> list[dict]:
    found = []
    for name in settings.COMPETITOR_NAMES:
        for line in _sentences(text):
            if re.search(rf"\b{re.escape(name)}\b", line, re.IGNORECASE):
                found.append(_violation(
                    RULE_COMPETITORS, f'This names a competitor ("{name}"). Remove it.', line))
                break
    return found


# --- Offer validity: 30 days from issuance ----------------------------------

VALIDITY = re.compile(
    r"valid(?:ity)?[^.;\n]{0,60}?30\)?\s*(?:calendar\s+)?days?|"
    r"30\)?\s*(?:calendar\s+)?days?[^.;\n]{0,60}?(?:valid|validity|issuance)",
    re.IGNORECASE,
)


def check_offer_validity(text: str) -> list[dict]:
    if VALIDITY.search(text or ""):
        return []
    return [_violation(
        RULE_VALIDITY,
        f"Missing the offer validity period. Say the offer is valid for "
        f"{settings.OFFER_VALIDITY_DAYS} days from issuance.",
    )]


RULES = {
    RULE_PRICE: {
        "text": "Every price must be expressed in both COP and USD.",
        "applies_to": ALL,
        "check": check_price_dual_currency,
    },
    RULE_PILLARS: {
        "text": "The proposal must mention the brand's three pillars: consistent quality, warm experience, speed of service.",
        "applies_to": MARKETING_ONLY,
        "check": check_brand_pillars,
    },
    RULE_SETUP: {
        "text": f"No section may promise setup or delivery in fewer than {settings.MIN_SETUP_BUSINESS_DAYS} business days.",
        "applies_to": ALL,
        "check": check_setup_time,
    },
    RULE_COMPETITORS: {
        "text": "No proposal may mention competitors by name.",
        "applies_to": ALL,
        "check": check_no_competitors,
    },
    RULE_VALIDITY: {
        "text": f"Every proposal must include an offer validity period ({settings.OFFER_VALIDITY_DAYS} days from issuance).",
        "applies_to": MARKETING_ONLY,
        "check": check_offer_validity,
    },
}


def check_compliance(department_id: str, text: str) -> dict:
    """Run every rule that applies to this department's section.

    Returns {"pass": bool, "rule_ids": [...], "violations": [...]}, the
    "compliance" part of the EvaluationResult.
    """
    violations = []
    for rule in RULES.values():
        if rule["applies_to"] != ALL and department_id not in rule["applies_to"]:
            continue
        violations.extend(rule["check"](text))
    return {
        "pass": not violations,
        "rule_ids": sorted({v["rule_id"] for v in violations}),
        "violations": violations,
    }


# --- One extra rule, from CONTEXT section 2.3 ("never invent numbers") -----------
# It needs the RFP's facts to check against, so evaluators.py runs it
# (check_no_invented_numbers); it is listed here so its text can be found.
RULE_NUMBERS = "NO-INVENTED-NUMBERS"
EXTRA_RULE_TEXT = {
    RULE_NUMBERS: (
        "Never invent a number: every figure must come from the RFP details or "
        "the department's key aspects (CONTEXT section 2.3). If a figure is not "
        "known, write \"to be confirmed\"."
    ),
}


def rule_text(rule_id: str) -> str:
    """The plain-English text of any rule id."""
    if rule_id in RULES:
        return RULES[rule_id]["text"]
    return EXTRA_RULE_TEXT.get(rule_id, rule_id)
