"""
synthesizer.py -- stage 5 of the RFP intake pipeline (Milestone 9, Part 1).

Takes the finished department sections and builds the Sales-facing summary:
what each department needs and who to ask.

Two parts, on purpose:
  1. The per-department list (owner, key aspects, open questions) is built
     here in CODE from the worker sections. The owner names come from
     CONTEXT-brasaland.md section 2.1 and are fixed, so the model can't
     invent a contact.
  2. The overview (2-3 sentences) is written by the model. It gets the same
     "never invent numbers" check the workers have. If the overview
     contains a number that isn't in the source, we use a plain template
     overview instead and record that in overview_source.
"""

import json

from . import llm
from .state import DEPARTMENT_IDS
from .workers import _numbers

# Fixed owners, from CONTEXT-brasaland.md section 2.1.
OWNERS = {
    "marketing": "Camila Ospina",
    "operaciones": "Felipe Guerrero",
    "procurement": "Lucia Fernandez",
    "training": "Jake Morrison",
}

SYSTEM_PROMPT = """You write the summary for the Sales team at Brasaland, a \
grilled-food restaurant chain. Sales will read your summary INSTEAD of the \
original RFP, so it must be clear and honest.

Write 2 to 3 plain English sentences that say: who the client is, what they \
want, which departments are involved, and the biggest thing that is still \
unknown.

Use ONLY the details you are given. Never invent or add a number, date, price \
or name.

Reply with JSON only, no other text:
{"overview": "..."}"""


def build_department_list(sections: dict) -> list[dict]:
    """One entry per department that ran, always in the same order."""
    return [
        {
            "department_id": dept,
            "owner": OWNERS[dept],
            "key_aspects": sections[dept]["key_aspects"],
            "open_questions": sections[dept]["open_questions"],
        }
        for dept in DEPARTMENT_IDS
        if dept in sections
    ]


def template_overview(metadata: dict, departments: list[dict]) -> str:
    """A plain overview built without the model. Used if the model's
    overview can't be trusted."""
    client = metadata.get("client_name") or "An unnamed client"
    service = metadata.get("service_type") or "a service"
    place = metadata.get("location")
    names = ", ".join(d["department_id"] for d in departments)
    open_count = sum(len(d["open_questions"]) for d in departments)

    text = f"{client} is asking for {service}"
    if place:
        text += f" in {place}"
    text += f". Departments involved: {names}. There are {open_count} open questions across them."
    return text


def synthesize(metadata: dict, sections: dict, missing_fields: list, other_departments: list) -> dict:
    departments = build_department_list(sections)

    prompt = (
        "RFP details (JSON):\n"
        + json.dumps(metadata, ensure_ascii=False)
        + "\n\nDepartment sections (JSON):\n"
        + json.dumps(departments, ensure_ascii=False)
        + "\n\nDetails missing from the RFP: "
        + (", ".join(missing_fields) if missing_fields else "none")
    )

    overview, source = None, "model"
    try:
        answer = llm.ask_json(prompt, system=SYSTEM_PROMPT)
        overview = str(answer.get("overview") or "").strip()
    except llm.LlmJsonError:
        overview = None  # model reply was unusable: fall back below

    # Numbers allowed in the overview: the ones in the metadata and sections.
    allowed_text = " ".join(str(v) for v in metadata.values() if v)
    for dept in departments:
        allowed_text += " " + " ".join(dept["key_aspects"] + dept["open_questions"])
    allowed = _numbers(allowed_text)

    if not overview or not _numbers(overview) <= allowed:
        overview, source = template_overview(metadata, departments), "template"

    return {
        "overview": overview,
        "overview_source": source,
        "departments": departments,
        "missing_fields": list(missing_fields),
        "other_departments_mentioned": list(other_departments),
        "total_open_questions": sum(len(d["open_questions"]) for d in departments),
    }


def synthesize_node(state: dict) -> dict:
    """The graph step. Reads metadata + sections, fills sales_summary."""
    summary = synthesize(
        state["metadata"],
        state["sections"],
        state.get("missing_fields", []),
        state.get("other_departments_mentioned", []),
    )
    return {"sales_summary": summary}
