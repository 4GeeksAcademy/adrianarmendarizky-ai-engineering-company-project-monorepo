"""
rfp_approval_service.py -- connects the approval workflow to the database
(Milestone 9, Part 3).

The workflow itself (data/pipelines/rfp_approval/, class ApprovalSystem) knows
nothing about the database. This module is the glue:

  - one ApprovalSystem for the whole server, saving its pauses in a SQLite file
  - the trace sink: every node execution becomes a row in rfp_events
  - after every change, copy what the workflow now says into the tables the
    screens read (rfp_approvals, rfp_department_sections, rfp_tickets,
    rfp_final_documents) and set the ticket's status

The workflow's own saved state is the source of truth. The tables are a copy
for listing and history, rewritten from it after each action.
"""

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, delete, select

import database
from rfp_models import (
    DepartmentSection, RfpApproval, RfpEvent, RfpFinalDocument, RfpTicket,
    STATUS_DONE, STATUS_NEEDS_HUMAN_REVIEW, STATUS_UNDER_EVALUATION, STATUS_WAITING_FOR_APPROVAL,
)
from routes.rfp import _load_handoff  # Part 1's saved handoff (services/api/routes/rfp.py)
from rfp_trace_store import store_event as _store_event  # the one place trace events are saved

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_approval import settings  # noqa: E402
from rfp_approval.checkpoint import get_checkpointer  # noqa: E402
from rfp_approval.final_document import render_markdown  # noqa: E402
from rfp_approval.reviser import make_loop_reviser, summarize_evaluation  # noqa: E402
from rfp_approval.system import ApprovalSystem, UnknownTicket  # noqa: E402

# What the workflow says happened -> the ticket's status (CONTEXT section 2.3).
WAITING_OUTCOMES = {"waiting_for_approval", "waiting_for_ceo", "arbitration_pending", "changes_forced", "blocked"}


class NotReadyToSend(Exception):
    """The ticket can't be sent for approval yet (the message says why)."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse(value):
    return datetime.fromisoformat(value) if value else None


# --- the one ApprovalSystem ---------------------------------------------------------------

_system = None
_system_lock = threading.Lock()


def _context_for(ticket_id: int, subject: str) -> dict:
    """What the reviser needs to rewrite a section: the same Part 1 facts the first draft used."""
    with Session(database.engine) as db:
        ticket = db.get(RfpTicket, ticket_id)
        metadata, inputs = _load_handoff(db, ticket)
    section = inputs.get(subject, {})
    return {"metadata": metadata, "key_aspects": section.get("key_aspects", []),
            "open_questions": section.get("open_questions", [])}


# (trace events are saved by rfp_trace_store.py)


def get_system() -> ApprovalSystem:
    global _system
    with _system_lock:
        if _system is None:
            _system = ApprovalSystem(get_checkpointer(), make_loop_reviser(_context_for), sink=_store_event)
        return _system


def use_system(system) -> None:
    """Swap the ApprovalSystem (the tests do; passing None goes back to the real one)."""
    global _system
    with _system_lock:
        _system = system


# --- sending a ticket for approval --------------------------------------------------------

def open_approvals(db: Session, ticket: RfpTicket) -> dict:
    sections = db.exec(select(DepartmentSection).where(DepartmentSection.ticket_id == ticket.id)).all()
    if not sections:
        raise NotReadyToSend("This ticket has no department sections.")
    missing = sorted(s.department_id for s in sections if not (s.draft_content or "").strip())
    if missing:
        raise NotReadyToSend(
            f"These sections have no draft yet: {', '.join(missing)}. Generate the drafts first.")

    metadata, inputs = _load_handoff(db, ticket)
    payload = {
        s.department_id: {
            "draft_content": s.draft_content,
            "evaluation": summarize_evaluation(s.evaluation_results),
            "card": {"key_aspects": inputs[s.department_id]["key_aspects"],
                     "open_questions": inputs[s.department_id]["open_questions"]},
        }
        for s in sections
    }

    system = get_system()
    system.reset_ticket(ticket.id)                      # a fresh start: forget any earlier round
    db.exec(delete(RfpApproval).where(RfpApproval.ticket_id == ticket.id))
    db.exec(delete(RfpFinalDocument).where(RfpFinalDocument.ticket_id == ticket.id))
    db.commit()

    outcome = system.open_ticket(ticket.id, metadata, payload)
    record_outcome(db, ticket, outcome)
    return outcome


# --- copying the workflow's state into the tables -----------------------------------------

def _ticket_status(outcome: dict):
    name = outcome["outcome"]
    if name == "done":
        return STATUS_DONE
    if name in ("department_rejected", "ceo_rejected"):
        return STATUS_NEEDS_HUMAN_REVIEW
    return STATUS_WAITING_FOR_APPROVAL


def _rejection_message(view: dict, outcome: dict):
    parts = []
    for entry in view["approvers"]:
        if entry["status"] == settings.REJECTED:
            who = "The CEO" if entry["subject"] == settings.CEO_SUBJECT else entry["subject"]
            parts.append(f"{who} ({entry['approver']}) rejected: {entry['rejected_reason'] or entry['comments']}")
    return " | ".join(parts) or None


def record_outcome(db: Session, ticket: RfpTicket, outcome: dict) -> None:
    system = get_system()
    view = system.describe(ticket.id)
    now = _now()
    sections = {s.department_id: s for s in db.exec(
        select(DepartmentSection).where(DepartmentSection.ticket_id == ticket.id)).all()}
    existing = {a.subject: a for a in db.exec(
        select(RfpApproval).where(RfpApproval.ticket_id == ticket.id)).all()}

    for entry in view["approvers"]:
        subject = entry["subject"]
        decided_at = _parse(entry["decided_at"]) if entry["status"] != settings.PENDING else None
        row = existing.get(subject) or RfpApproval(ticket_id=ticket.id, subject=subject, approver=entry["approver"])
        row.status = entry["status"]
        row.approver = entry["approver"]
        row.acted_by = entry["acted_by"]
        row.comments = entry["rejected_reason"] or entry["comments"] or None
        row.estimates = entry["estimates"] or None
        row.revision_count = entry["revision_count"]
        row.decided_at = decided_at
        row.updated_at = now
        db.add(row)

        section = sections.get(subject)
        if section is not None:
            section.approval_status = entry["status"]
            section.approver = entry["approver"]
            section.approved_at = decided_at if entry["status"] == settings.APPROVED else None
            if entry["draft_content"]:
                section.draft_content = entry["draft_content"]
            if entry["revision_count"] > 0 and entry["evaluation"]:
                section.evaluation_results = {
                    **(section.evaluation_results or {}), **entry["evaluation"],
                    "revisions_requested": entry["revision_count"],
                }
            db.add(section)

    ticket.status = _ticket_status(outcome)
    ticket.error_message = _rejection_message(view, outcome) if ticket.status == STATUS_NEEDS_HUMAN_REVIEW else None
    ticket.updated_at = now
    db.add(ticket)

    if outcome["outcome"] == "done":
        document = outcome["document"]
        stored = db.exec(select(RfpFinalDocument).where(RfpFinalDocument.ticket_id == ticket.id)).first() \
            or RfpFinalDocument(ticket_id=ticket.id, markdown="")
        stored.sections = document["sections"]
        stored.approvals = document["approvals"]
        stored.total_estimated_value = document["total_estimated_value"]
        stored.markdown = render_markdown(document)
        stored.generated_at = _parse(document["generated_at"]) or now
        db.add(stored)
    db.commit()


# --- what the screens read ------------------------------------------------------------------

def approvals_payload(db: Session, ticket: RfpTicket) -> dict:
    payload = {"ticket_id": ticket.id, "status": ticket.status, "started": False, "approvers": [],
               "arbitration": None, "conflicts": [], "warnings": [], "revision_limit": settings.REVISION_LIMIT,
               "document_ready": ticket.status == STATUS_DONE, "message": ticket.error_message}
    # An earlier round of approvals only counts while it is running (waiting_for_approval), finished
    # (done), or was just ended by a rejection (needs_human_review, with the reason). Once new drafts
    # exist the old round is void, and the screen must not show it.
    if ticket.status == STATUS_UNDER_EVALUATION or (ticket.status == STATUS_NEEDS_HUMAN_REVIEW and not ticket.error_message):
        return payload
    try:
        view = get_system().describe(ticket.id)
    except UnknownTicket:
        return payload
    payload.update(view)
    payload["started"] = True
    return payload


def slim_outcome(outcome: dict) -> dict:
    """The outcome for a response: the document itself has its own endpoint."""
    return {**{k: v for k, v in outcome.items() if k != "document"}, "document_ready": outcome["document"] is not None}


def final_document_payload(db: Session, ticket_id: int):
    row = db.exec(select(RfpFinalDocument).where(RfpFinalDocument.ticket_id == ticket_id)).first()
    if row is None:
        return None
    return {"ticket_id": ticket_id, "sections": row.sections, "approvals": row.approvals,
            "total_estimated_value": row.total_estimated_value, "generated_at": row.generated_at.isoformat(),
            "markdown": row.markdown}


def trace_payload(db: Session, ticket_id: int, limit: int) -> list[dict]:
    rows = db.exec(select(RfpEvent).where(RfpEvent.ticket_id == ticket_id).order_by(RfpEvent.id).limit(limit)).all()
    return [{"id": r.id, "part": r.part, "agent": r.agent, "event_type": r.event_type, "subject": r.subject,
             "actor": r.actor, "input": r.input_data, "output": r.output_data,
             "created_at": r.created_at.isoformat()} for r in rows]
