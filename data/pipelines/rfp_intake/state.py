"""
state.py -- the data that travels through the RFP intake graph (Part 1).

Same idea as services/api/agent/state.py, but this is its own state:
the RFP graph never shares anything with the support agent's graph.

Each stage fills in its own fields and leaves the rest alone.
"""

from typing import TypedDict


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

    # Stage 4: workers and synthesizer (added later)
    sections: dict
    sales_summary: dict

    # Set if any stage crashes, so the ticket can say "failed"
    error: str | None
