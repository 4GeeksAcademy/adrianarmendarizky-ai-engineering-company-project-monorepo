"""
orchestrator.py -- stage 3 of the RFP intake pipeline (Milestone 9, Part 1).

Reads the Markdown of an RFP that the classifier accepted and returns:
  - metadata: client, location, service type, scope, deadline, budget
  - which of the four departments apply (CONTEXT-brasaland.md section 2.1)
  - for each department, a short extract of the document it needs
  - missing_fields: things the RFP does not say

Rules from CONTEXT:
  - Not every RFP needs all four departments. The model decides.
  - Never invent numbers. Anything the RFP does not say stays empty and is
    listed in missing_fields. That list is built here in code, from the
    empty fields, not by trusting the model.
  - A department that is not one of the four is ignored, and its name is
    saved in other_departments_mentioned so Sales can see it.
  - Marketing owns every ticket, so it is always included.
"""

import re

from . import llm
from .state import DEPARTMENT_IDS

MAX_CHARS = 15000

# Fields we report as "missing" when the RFP does not give them.
TRACKED_FIELDS = (
    "client_name", "location", "service_type", "scope", "deadline", "budget_range",
)

SYSTEM_PROMPT = """You are the intake orchestrator for Brasaland, a grilled-food \
restaurant chain with locations in Colombia and Florida. A document has already \
been accepted as a request for a proposal (RFP). The document may be in English \
or Spanish. Always write in English, but copy names, dates and amounts exactly \
as they appear in the document.

Step 1 - Extract these fields. Use null for anything the document does not say. \
NEVER guess or invent a number, date, name or amount.
- rfp_id: the reference number, if there is one
- client_name: the organization or person asking
- location: where the service is needed (city, country or state)
- service_type: a few words, for example "co-branded concession", "recurring catering"
- scope: one or two sentences with the volume or size (people, locations, how \
often, contract length). Only include numbers that appear in the document.
- deadline: the response deadline, copied exactly as written
- budget_range: the budget or contract value, copied exactly as written

Step 2 - Decide which departments apply. Use ONLY these ids:
- "marketing": brand terms, exclusivity, co-branding, offer validity. It owns \
every ticket, so it ALWAYS applies.
- "operaciones": can we deliver it? Kitchen and staff capacity, setup time, \
cost per event. Applies to any request that needs food to be prepared or served.
- "procurement": ingredient cost based on volume, supplier lead times. Applies \
whenever Brasaland will prepare or serve food for the request, because that \
food has to be bought. That includes catering, concessions and events.
- "training": ONLY when the request needs a NEW recipe, a new menu item, or a \
new standard that staff must be certified on. Do NOT include it when the \
request uses the standard menu.

For each department that applies give:
- "reason": one plain sentence on why it applies
- "extract": the exact sentences from the document that this department needs. \
Copy them word for word, whole sentences only, one per line. Do not use "..." \
and do not change any words. Do not add anything.

If the document mentions a department that is not one of the four ids above \
(for example Finance or Legal), do NOT add it to "departments". Put its name in \
"other_departments_mentioned".

Reply with JSON only, no other text:
{"rfp_id": null, "client_name": null, "location": null, "service_type": null, \
"scope": null, "deadline": null, "budget_range": null, \
"departments": {"marketing": {"reason": "", "extract": ""}}, \
"other_departments_mentioned": []}"""


def _clean(value):
    """Turn empty or 'not given' answers into None."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in ("", "null", "none", "n/a", "not specified", "unknown"):
        return None
    return text


def _squash(text: str) -> str:
    """Lowercase and keep only letters and digits, so bullets, dashes,
    quote marks, line breaks and spacing can't make a real quote look fake."""
    return re.sub(r"[\W_]+", "", text.lower())


def _is_verbatim(extract: str, doc: str) -> bool:
    """True if every piece of the extract really appears in the document.

    The model may give several sentences, one per line or split by "...",
    so each piece is checked on its own. Tiny pieces are ignored.
    """
    pieces = [p for p in re.split(r"\n+|\.\.\.|\u2026", extract) if len(_squash(p)) >= 8]
    if not pieces:
        return False
    doc_squashed = _squash(doc)
    return all(_squash(p) in doc_squashed for p in pieces)


def orchestrate_rfp(markdown: str, language: str = "en") -> dict:
    doc = markdown[:MAX_CHARS]
    prompt = f"Document (Markdown):\n---\n{doc}\n---"
    answer = llm.ask_json(prompt, system=SYSTEM_PROMPT)

    # 1. Metadata
    metadata = {"rfp_id": _clean(answer.get("rfp_id"))}
    for field in TRACKED_FIELDS:
        metadata[field] = _clean(answer.get(field))
    metadata["language"] = language

    # 2. Departments
    raw_departments = answer.get("departments")
    if not isinstance(raw_departments, dict):
        raise llm.LlmJsonError(f"'departments' must be an object, got: {raw_departments!r}")

    other = []
    for name in answer.get("other_departments_mentioned") or []:
        if _clean(name):
            other.append(str(name).strip())

    assignments = {}
    for name, info in raw_departments.items():
        key = str(name).strip().lower()
        if key not in DEPARTMENT_IDS:
            other.append(str(name).strip())  # not one of ours: report it, do not route to it
            continue
        info = info if isinstance(info, dict) else {}
        extract = _clean(info.get("extract")) or ""
        # The extract must really be in the document. If the model
        # rewrote it or made it up, hand the worker the full document instead.
        verbatim = _is_verbatim(extract, doc)
        assignments[key] = {
            "reason": _clean(info.get("reason")) or "",
            "extract": extract if verbatim else doc,
            "extract_is_verbatim": verbatim,
        }

    # Marketing owns every ticket (CONTEXT section 2.1).
    if "marketing" not in assignments:
        assignments["marketing"] = {
            "reason": "Marketing owns every ticket.",
            "extract": doc,
            "extract_is_verbatim": False,
        }

    # Always the same order, whatever order the model used.
    ordered = {d: assignments[d] for d in DEPARTMENT_IDS if d in assignments}

    return {
        "metadata": metadata,
        "departments_needed": list(ordered.keys()),
        "assignments": ordered,
        # Built here from the empty fields, not taken from the model.
        "missing_fields": [f for f in TRACKED_FIELDS if metadata[f] is None],
        "other_departments_mentioned": list(dict.fromkeys(other)),
    }


def orchestrate_node(state: dict) -> dict:
    """The graph step. Reads markdown + language, fills the stage-3 fields."""
    return orchestrate_rfp(state["markdown"], state.get("language", "en"))
