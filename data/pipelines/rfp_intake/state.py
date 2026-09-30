"""
state.py -- the data that travels through the RFP intake graph (Part 1).

Same idea as services/api/agent/state.py, but this is its own state:
the RFP graph never shares anything with the support agent's graph.

Each stage fills in its own fields and leaves the rest alone.
"""

import operator
from typing import Annotated, TypedDict


def _first(current, new):
    """If two parallel workers both fail, keep the first error message."""
    return current or new


class RfpIntakeState(TypedDict, total=False):
    # Comes in with the upload
    ticket_id: int
    pdf_path: str

    # Stage 1: convert (convert.py)
    markdown: str
    language: str  # "en" or "es"
    readability: dict

    # Stage 2: classifier (classifier.py)
    is_rfp: bool
    discard_reason: str | None

    # Stage 3: orchestrator (added in the next step)
    metadata: dict
    departments_needed: list[str]
    assignments: dict  # department_id -> {"reason", "extract", "extract_is_verbatim"}
    missing_fields: list[str]
    other_departments_mentioned: list[str]

    # Stage 4: workers and synthesizer (added later)
    # Each worker adds its own department. operator.or_ merges the dicts.
    sections: Annotated[dict, operator.or_]
    sales_summary: dict

    # Set if any stage crashes, so the ticket can say "failed"
    error: Annotated[str | None, _first]

    # Set at the very end by run_intake(): intake_complete / discarded / failed
    status: str


# The four departments (CONTEXT-brasaland.md section 2.1). Use these exact
# strings everywhere. "operaciones" is Spanish on purpose.
DEPARTMENT_IDS = ("marketing", "operaciones", "procurement", "training")
