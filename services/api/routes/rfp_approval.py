"""
routes/rfp_approval.py -- the Part 3 side of the RFP API (Milestone 9): send a
ticket for approval, record each approver's decision, settle conflicts, read the
final document and the trace of everything that happened.

    POST /rfp/tickets/{id}/send-for-approval            open the approvals
    GET  /rfp/tickets/{id}/approvals                    who must approve, what they see, where it stands
    POST /rfp/tickets/{id}/approvals/{subject}          an approver decides (approve / reject / request_changes)
    POST /rfp/tickets/{id}/approvals/{subject}/continue pick up a rewrite that was cut short
    POST /rfp/tickets/{id}/arbitration/{trigger}        the named arbiter answers a cost-vs-feasibility conflict
    GET  /rfp/tickets/{id}/final-document               the final proposal, once everyone approved
    GET  /rfp/tickets/{id}/trace                        every step, in order

Who may decide: managers and admins, the same bar as agent memory (routes/agent.py).
The ticket's status is only ever waiting_for_approval, done, or back to
needs_human_review (CONTEXT section 2.3).
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel import Session, select

import rfp_approval_service as service
from database import get_db
from dependencies import get_current_user
from rfp_models import (
    DepartmentSection, RfpTicket,
    STATUS_NEEDS_HUMAN_REVIEW, STATUS_UNDER_EVALUATION, STATUS_WAITING_FOR_APPROVAL,
)
from routes.rfp import _generation_running
from user_models import Role, User

from rfp_approval.decisions import InvalidDecision
from rfp_approval.system import NotWaiting, UnknownTicket

router = APIRouter(prefix="/rfp", tags=["rfp-approval"])

# Who may record an approval: the people the approvals are for, plus admins.
APPROVAL_ROLES = (Role.MANAGER, Role.ADMIN)
CAN_SEND_FOR_APPROVAL = (STATUS_UNDER_EVALUATION, STATUS_NEEDS_HUMAN_REVIEW)


def _ticket_or_404(db: Session, ticket_id: int) -> RfpTicket:
    ticket = db.get(RfpTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def _require_approver(user: User) -> None:
    if user.role not in APPROVAL_ROLES:
        raise HTTPException(status_code=403, detail="Only managers and admins can record approvals.")


def _must_be_waiting(ticket: RfpTicket) -> None:
    if ticket.status != STATUS_WAITING_FOR_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"This ticket is not waiting for approval (status: {ticket.status}).")


def _translate(error: Exception) -> HTTPException:
    """The workflow's own refusals, as HTTP answers a screen can show."""
    if isinstance(error, InvalidDecision):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, (NotWaiting, service.NotReadyToSend)):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, UnknownTicket):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, RuntimeError):
        return HTTPException(
            status_code=502,
            detail=f"{error} Nothing was lost: the approval is exactly where it was. "
                   f"Use 'continue' on that approver to try the rewrite again.")
    raise error


def _answer(db: Session, ticket: RfpTicket, outcome: dict) -> dict:
    return {"outcome": service.slim_outcome(outcome), "approvals": service.approvals_payload(db, ticket)}


@router.post("/tickets/{ticket_id}/send-for-approval")
def send_for_approval(ticket_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    ticket = _ticket_or_404(db, ticket_id)
    if ticket.status not in CAN_SEND_FOR_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Only a ticket with finished drafts can be sent for approval (status: {ticket.status}).")
    sections = db.exec(select(DepartmentSection).where(DepartmentSection.ticket_id == ticket.id)).all()
    if _generation_running(ticket, sections):
        raise HTTPException(status_code=409, detail="The drafts are still being written. Wait until they finish.")
    try:
        outcome = service.open_approvals(db, ticket)
    except Exception as error:
        raise _translate(error)
    return _answer(db, ticket, outcome)


@router.get("/tickets/{ticket_id}/approvals")
def get_approvals(ticket_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return service.approvals_payload(db, _ticket_or_404(db, ticket_id))


@router.post("/tickets/{ticket_id}/approvals/{subject}")
def record_decision(
    ticket_id: int, subject: str, body: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    _require_approver(current_user)
    ticket = _ticket_or_404(db, ticket_id)
    _must_be_waiting(ticket)
    try:
        outcome = service.get_system().decide(ticket.id, subject, body, current_user.email)
        service.record_outcome(db, ticket, outcome)
    except Exception as error:
        raise _translate(error)
    return _answer(db, ticket, outcome)


@router.post("/tickets/{ticket_id}/approvals/{subject}/continue")
def continue_rewrite(
    ticket_id: int, subject: str,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    _require_approver(current_user)
    ticket = _ticket_or_404(db, ticket_id)
    _must_be_waiting(ticket)
    try:
        outcome = service.get_system().continue_subject(ticket.id, subject)
        service.record_outcome(db, ticket, outcome)
    except Exception as error:
        raise _translate(error)
    return _answer(db, ticket, outcome)


@router.post("/tickets/{ticket_id}/arbitration/{trigger}")
def answer_arbitration(
    ticket_id: int, trigger: str, body: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    _require_approver(current_user)
    ticket = _ticket_or_404(db, ticket_id)
    _must_be_waiting(ticket)
    try:
        outcome = service.get_system().answer_arbitration(ticket.id, trigger, body, current_user.email)
        service.record_outcome(db, ticket, outcome)
    except Exception as error:
        raise _translate(error)
    return _answer(db, ticket, outcome)


@router.get("/tickets/{ticket_id}/final-document")
def get_final_document(ticket_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    _ticket_or_404(db, ticket_id)
    document = service.final_document_payload(db, ticket_id)
    if document is None:
        raise HTTPException(status_code=404, detail="The final document does not exist yet: not everyone has approved.")
    return document


@router.get("/tickets/{ticket_id}/trace")
def get_trace(
    ticket_id: int, limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db), _user: User = Depends(get_current_user),
):
    _ticket_or_404(db, ticket_id)
    return service.trace_payload(db, ticket_id, limit)
