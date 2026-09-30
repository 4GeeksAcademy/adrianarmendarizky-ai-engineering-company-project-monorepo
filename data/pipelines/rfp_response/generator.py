"""
generator.py -- the department generator agents (Milestone 9, Part 2).

One generator per department (the four ids in CONTEXT-brasaland.md section
2.1). Each one writes that department's section of the pricing proposal from
what Part 1 already found: the RFP details, the department's key_aspects and
open_questions. The PDF is never read again.

Every generator gets the CONTEXT section 5 guidelines that apply to its
department in its instructions (see GUIDELINE_TEXT), so most drafts pass on
the first try. The evaluators still check; the instructions just make a fail
less likely.

The model never works out prices. Where the RFP gives an amount, facts.py
converts it in code and the generator copies the result. Where a figure is
unknown, the draft says "to be confirmed by <owner>".

The same function is used for a first draft and for a revision: a revision
also gets the previous draft and the evaluators' feedback_for_generator.
"""

import json
import re

from rfp_intake import llm
from rfp_intake.synthesizer import OWNERS

from . import facts, rules, settings

DEPARTMENTS = {
    "marketing": {
        "title": "Brand and Commercial Terms",
        "focus": (
            "Brand and commercial terms: who the client is, the offer in brief, "
            "exclusivity and co-branding terms if the RFP asks for them, the "
            "brand pillars, and how long the offer is valid."
        ),
    },
    "operaciones": {
        "title": "Operations and Delivery",
        "focus": (
            "Operational feasibility: how Brasaland would run the service, "
            "kitchen and staff capacity, sites and schedule, setup time, and "
            "the cost per event or per site."
        ),
    },
    "procurement": {
        "title": "Ingredient Costs and Supply",
        "focus": (
            "Ingredient cost and supply: what drives the ingredient cost "
            "(volume, frequency, menu), supplier lead times (say they are to be "
            "confirmed unless the facts give them), and how the "
            "estimated cost will be confirmed."
        ),
    },
    "training": {
        "title": "Training and Certification",
        "focus": (
            "Training and certification: any new recipe or standard, who must "
            "be certified, and how long development and certification take."
        ),
    },
}

# What each CONTEXT section 5 rule means for the writer. Only the rules that
# apply to the department are put in its instructions.
GUIDELINE_TEXT = {
    rules.RULE_PRICE: (
        "Show every price in BOTH COP and USD, in the same sentence. "
        "Copy the figures from 'Currency figures' exactly; never convert anything yourself."
    ),
    rules.RULE_PILLARS: (
        "Mention the three brand pillars by name, using these exact words: "
        + ", ".join(settings.BRAND_PILLARS) + "."
    ),
    rules.RULE_SETUP: (
        f"If you mention a setup or delivery time, it must be at least "
        f"{settings.MIN_SETUP_BUSINESS_DAYS} business days. If the facts give "
        f"no time, do not promise one."
    ),
    rules.RULE_COMPETITORS: "Never mention another restaurant or catering company by name.",
    rules.RULE_VALIDITY: (
        f"State that the offer is valid for {settings.OFFER_VALIDITY_DAYS} days from issuance."
    ),
}


def guidelines_for(department_id: str) -> list[str]:
    lines = []
    for rule_id, rule in rules.RULES.items():
        if rule["applies_to"] == rules.ALL or department_id in rule["applies_to"]:
            lines.append(GUIDELINE_TEXT[rule_id])
    return lines


def _system_prompt(department_id: str) -> str:
    info = DEPARTMENTS[department_id]
    owner = OWNERS[department_id]
    guideline_lines = "\n".join(f"- {line}" for line in guidelines_for(department_id))
    return f"""You are drafting one section of a pricing proposal for Brasaland, a \
grilled-food restaurant chain with locations in Colombia and Florida. This section \
belongs to the {info['title']} department. Write in English, in short plain sentences, \
addressed to the client.

Department focus: {info['focus']}

Rules:
- Use ONLY the facts you are given. Never invent a number, date, price, name or promise.
- If the proposal needs a figure that is not in the facts (a price, a quantity, a \
time), write "to be confirmed by {owner}" instead of a number.
- Cover every key aspect that the client should get an answer to.
{guideline_lines}
- Use short paragraphs and bullets that start with "-". Do not use numbered lists.
- Start with the heading line: ## {info['title']}
- If open questions are given, end with a bullet list called "Points to confirm with \
the client", using those questions. Do not add others.

Reply with the section text only."""


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def build_prompt(department_id, metadata, key_aspects, open_questions,
                 previous_draft=None, feedback=None) -> str:
    figures = facts.currency_figures(metadata)
    if figures:
        figure_block = (
            _bullets(figures, "")
            + f"\n(Reference rate: 1 USD = {settings.COP_PER_USD:,.0f} COP. "
            "It is a reference rate; say it is to be confirmed.)"
        )
    else:
        figure_block = "none: the RFP gives no amount we can convert."

    prompt = (
        "Shared RFP details (JSON):\n"
        + json.dumps(facts.shared_details(metadata), ensure_ascii=False)
        + "\n\nKey aspects for this department:\n"
        + _bullets(key_aspects, "none")
        + "\n\nOpen questions for this department:\n"
        + _bullets(open_questions, "none")
        + "\n\nCurrency figures:\n"
        + figure_block
    )
    if previous_draft and feedback:
        prompt += (
            "\n\nYour previous draft:\n---\n" + previous_draft
            + "\n---\n\nThe reviewers found these problems. Write the new draft so "
            "that every one is fixed, and keep everything that was already fine:\n"
            + feedback
        )
    return prompt


def generate_draft(department_id: str, metadata: dict, key_aspects: list[str],
                   open_questions: list[str], *, previous_draft: str | None = None,
                   feedback: str | None = None) -> str:
    """Write (or rewrite) one department's section. Returns the draft text."""
    if department_id not in DEPARTMENTS:
        raise ValueError(f"Unknown department: {department_id!r}")

    prompt = build_prompt(department_id, metadata, key_aspects, open_questions,
                          previous_draft, feedback)
    raw = llm.call_generation_llm(prompt, system=_system_prompt(department_id))

    # Models sometimes wrap text in ``` fences. Remove them.
    draft = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", (raw or "").strip(),
                   flags=re.IGNORECASE).strip()
    if not draft:
        raise ValueError(f"The generator for '{department_id}' returned an empty draft.")
    return draft
