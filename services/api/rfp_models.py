"""
rfp_models.py -- database tables for the RFP intake workflow (Milestone 9).

Three tables, all in Supabase (Postgres), same as the inventory tables:
  rfp_tickets              one row per uploaded PDF (the "ticket")
  rfp_metadata             what we pulled out of the RFP, one row per ticket
  rfp_department_sections  one row per department that applies to the RFP

Part 1 fills in the tickets, metadata, and key_aspects. The columns marked
"Part 2 / Part 3" stay empty for now. They exist already because
create_all() in database.py never alters a table that already exists.

Department ids and statuses come from CONTEXT-brasaland.md sections 2.1
and 2.3. Use these exact strings everywhere.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel

# The four departments (CONTEXT section 2.1). "operaciones" is Spanish on purpose.
DEPARTMENT_IDS = ("marketing", "operaciones", "procurement", "training")

# Ticket statuses used in Part 1. "failed" is our own addition: it is what
# the ticket says if the pipeline crashes, so it never stays "analyzing" forever.
STATUS_ANALYZING = "analyzing"
STATUS_DISCARDED = "discarded"
STATUS_INTAKE_COMPLETE = "intake_complete"
STATUS_FAILED = "failed"

# Part 2 statuses (CONTEXT-brasaland.md section 2.3)
STATUS_DRAFTING = "drafting"
STATUS_UNDER_EVALUATION = "under_evaluation"
STATUS_NEEDS_HUMAN_REVIEW = "needs_human_review"


def _now() -> datetime:
    # UTC time, stored without a timezone label (the columns have none).
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RfpTicket(SQLModel, table=True):
    __tablename__ = "rfp_tickets"

    id: Optional[int] = Field(default=None, primary_key=True)  # this is the ticket_id
    rfp_id: Optional[str] = Field(default=None, index=True)  # reference number from the RFP, if it has one
    status: str = Field(default=STATUS_ANALYZING, index=True)
    original_filename: str
    raw_pdf_path: str  # where the PDF was saved under data/raw/
    discard_reason: Optional[str] = None  # why the classifier said "not an RFP"
    error_message: Optional[str] = None  # filled in only when status = "failed"
    # The synthesizer's Sales-facing summary: what to ask whom.
    sales_summary: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class RfpMetadata(SQLModel, table=True):
    __tablename__ = "rfp_metadata"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="rfp_tickets.id", unique=True, index=True)
    client_name: Optional[str] = None
    location: Optional[str] = None
    service_type: Optional[str] = None
    scope: Optional[str] = None
    deadline: Optional[str] = None  # kept exactly as written in the document
    budget_range: Optional[str] = None
    language: Optional[str] = None  # "en" or "es"
    departments_needed: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Things the RFP does not say (never invent them): volume, budget, etc.
    missing_fields: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Readability. All three stay empty if the text is too short to score.
    word_count: Optional[int] = None
    flesch_kincaid: Optional[float] = None
    gunning_fog: Optional[float] = None
    readability_note: Optional[str] = None


class DepartmentSection(SQLModel, table=True):
    __tablename__ = "rfp_department_sections"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="rfp_tickets.id", index=True)
    department_id: str  # one of DEPARTMENT_IDS
    # Part 1: what this department needs to know, and what is still unknown.
    key_aspects: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    open_questions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Part 2 / Part 3: left empty in Part 1.
    draft_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    evaluation_results: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    approval_status: str = Field(default="pending")  # pending / approved / rejected
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Part 3: approvals, the trace, and the final document (Milestone 9)
# ---------------------------------------------------------------------------
# Three NEW tables. Nothing above this line changes: create_all() (database.py,
# init_inventory_db) creates new tables and never alters existing ones.

from sqlalchemy import UniqueConstraint  # noqa: E402

# Part 3 statuses (CONTEXT-brasaland.md section 2.3)
STATUS_WAITING_FOR_APPROVAL = "waiting_for_approval"
STATUS_DONE = "done"


class RfpApproval(SQLModel, table=True):
    """One row per approver of one ticket: each department that applies, plus
    the CEO when the estimated value is above $50,000 USD a year."""

    __tablename__ = "rfp_approvals"
    __table_args__ = (UniqueConstraint("ticket_id", "subject", name="one_approval_per_subject"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="rfp_tickets.id", index=True)
    subject: str  # a department id, or "ceo"
    status: str = Field(default="pending")  # pending / approved / rejected (CONTEXT 2.3)
    approver: str  # the owner named in CONTEXT (who SHOULD approve)
    acted_by: Optional[str] = None  # the logged-in user who actually clicked
    comments: Optional[str] = Field(default=None, sa_column=Column(Text))
    estimates: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    revision_count: int = 0  # how many times changes were requested (limit in the settings)
    decided_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class RfpEvent(SQLModel, table=True):
    """Append-only log: every node execution and every human action, with the
    agent, its input, its output and the time (the ticket's traceability rule).
    The same rows are the audit trail of who approved what, and when."""

    __tablename__ = "rfp_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="rfp_tickets.id", index=True)
    part: int  # 1 = intake, 2 = response generation, 3 = approval
    agent: str  # the node or agent that ran, or "human"
    event_type: str
    subject: Optional[str] = None  # department id, "ceo", or None for ticket-level events
    input_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    output_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    actor: Optional[str] = None  # the user's email for human actions
    created_at: datetime = Field(default_factory=_now, index=True)


class RfpFinalDocument(SQLModel, table=True):
    """The final proposal, stored once every approval is in (CONTEXT 2.3 FinalDocument)."""

    __tablename__ = "rfp_final_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="rfp_tickets.id", unique=True, index=True)
    sections: list = Field(default_factory=list, sa_column=Column(JSON))
    approvals: list = Field(default_factory=list, sa_column=Column(JSON))
    total_estimated_value: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    markdown: str = Field(sa_column=Column(Text))
    generated_at: datetime = Field(default_factory=_now)
