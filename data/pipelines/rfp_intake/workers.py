"""
workers.py -- stage 4 of the RFP intake pipeline (Milestone 9, Part 1).

One worker per department (CONTEXT-brasaland.md section 2.1). Each worker
receives ONLY:
  - the shared RFP metadata (client, location, deadline, budget, ...)
  - the extract the orchestrator picked for its department
It never sees the whole document or another department's extract.

Each worker returns:
  key_aspects       what this department needs to know or decide
  open_questions    what the RFP does not say that this department needs
  removed_unsupported  bullets thrown away because they contained a number
                       that is not in the extract or the metadata

The "never invent numbers" rule (CONTEXT section 2.3) is enforced in code,
not just in the prompt: see _number_is_supported().
"""

import json
import re

from . import llm
from .state import DEPARTMENT_IDS

MAX_ITEMS = 8  # per list, so one chatty answer can't flood the ticket

# Offer validity is fixed at 30 days by Brasaland (CONTEXT-brasaland.md
# section 5), so Sales must never ask the client about it.
OWN_KNOWLEDGE = re.compile(r"remain valid|stay valid|offer validity|validity period|vigencia", re.IGNORECASE)

COMMON_RULES = """You are a specialist at Brasaland, a grilled-food restaurant chain \
with locations in Colombia and Florida. A client sent a request for a proposal (RFP). \
You are given shared details about the RFP and the part of the text that matters \
to YOUR department. The text may be in English or Spanish. Always write in English.

Rules:
- Use ONLY the information you are given. Never invent a number, date, price, \
name or fact. Do not add details the text does not say (for example, do not \
mention a "trial period" unless the text does).
- "proposal_deadline" in the shared details is when the client wants the \
PROPOSAL. It is NOT a date the service starts, unless the text clearly says so.
- "service_location" is where the service is needed. It is not necessarily \
where the client is based.
- Only ask questions the CLIENT can answer. Do not ask about things Brasaland \
already knows itself, such as its own supplier lead times, its own offer \
validity period, or its own prices. Do not ask for anything the text already gives.
- If a number is written as a word in the text (for example "one year" or \
"un año"), keep it as a word. Do not turn it into digits.
- If something your department needs is not given, do NOT guess. Put it in \
"open_questions" as a short question Sales can ask the client.
- key_aspects: 2 to 6 short bullets, plain language, each one under 25 words.
- open_questions: 0 to 5 short questions.

Reply with JSON only, no other text:
{"key_aspects": ["..."], "open_questions": ["..."]}"""

FOCUS = {
    "marketing": (
        "Marketing (owner: Camila Ospina) owns the ticket. Look for: brand terms, "
        "exclusivity, co-branding, how long the offer should stay valid, the "
        "response deadline, and who the client contact is."
    ),
    "operaciones": (
        "Restaurant Operations (owner: Felipe Guerrero). Look for: can Brasaland "
        "deliver this? Kitchen and staff capacity, how many sites and how often, "
        "peak periods, setup time, and the cost of running each event or site."
    ),
    "procurement": (
        "Procurement and Suppliers (owner: Lucia Fernandez). Look for: how much "
        "food is needed (people, meals, frequency), what drives the ingredient "
        "cost, supplier lead times, and any budget the client mentions."
    ),
    "training": (
        "Training and Quality Standards (owner: Jake Morrison). Look for: any new "
        "recipe, menu item or standard that staff must be trained and certified "
        "on, and how long developing and certifying it could take."
    ),
}


def _system_prompt(department_id: str) -> str:
    return COMMON_RULES + "\n\nYour department: " + FOCUS[department_id]


def _numbers(text: str) -> set[str]:
    """All numbers in a text, reduced to their digits only.

    "$60,000" -> "60000", "2026." -> "2026", "60.000" -> "60000".
    """
    found = re.findall(r"\d[\d.,]*", text)
    return {re.sub(r"\D", "", n) for n in found}


def _number_is_supported(bullet: str, allowed: set[str]) -> bool:
    """A bullet is fine if every number in it also appears in the source."""
    return _numbers(bullet) <= allowed


def _as_text_list(value) -> list[str]:
    """Turn whatever the model gave us into a clean list of short strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = [str(v).strip() for v in value if str(v).strip()]
    return items[:MAX_ITEMS]


def run_worker(department_id: str, metadata: dict, extract: str) -> dict:
    """Run one department's worker and return its section."""
    if department_id not in DEPARTMENT_IDS:
        raise ValueError(f"Unknown department: {department_id!r}")

    # Renamed labels so the model can't misread them (deadline = proposal
    # deadline, not a start date; location = where the service happens).
    renames = {"deadline": "proposal_deadline", "location": "service_location"}
    shared = {renames.get(key, key): value for key, value in metadata.items()}

    prompt = (
        "Shared RFP details (JSON):\n"
        + json.dumps(shared, ensure_ascii=False)
        + "\n\nText from the RFP for your department:\n---\n"
        + extract
        + "\n---"
    )
    answer = llm.ask_json(prompt, system=_system_prompt(department_id))

    # Numbers that are allowed to appear: the ones in the extract or metadata.
    source = extract + " " + " ".join(str(v) for v in metadata.values() if v)
    allowed = _numbers(source)

    key_aspects, removed = [], []
    for bullet in _as_text_list(answer.get("key_aspects")):
        if _number_is_supported(bullet, allowed):
            key_aspects.append(bullet)
        else:
            removed.append(bullet)

    return {
        "department_id": department_id,
        "key_aspects": key_aspects,
        "open_questions": [
            q for q in _as_text_list(answer.get("open_questions"))
            if not OWN_KNOWLEDGE.search(q)
        ],
        "removed_unsupported": removed,
    }


# One named worker per department. Each is a small wrapper, so the graph can
# treat them as four separate workers and tests can call any one directly.
def marketing_worker(metadata: dict, extract: str) -> dict:
    return run_worker("marketing", metadata, extract)


def operaciones_worker(metadata: dict, extract: str) -> dict:
    return run_worker("operaciones", metadata, extract)


def procurement_worker(metadata: dict, extract: str) -> dict:
    return run_worker("procurement", metadata, extract)


def training_worker(metadata: dict, extract: str) -> dict:
    return run_worker("training", metadata, extract)


WORKERS = {
    "marketing": marketing_worker,
    "operaciones": operaciones_worker,
    "procurement": procurement_worker,
    "training": training_worker,
}
