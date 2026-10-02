"""
routes/rfp.py -- the HTTP side of the RFP workflow (Milestone 9).

Part 1 (intake), behind login (same get_current_user as /inventory):
  POST /rfp/tickets        upload one PDF. Saves it under data/raw/rfp_uploads/,
                           creates the ticket as "analyzing", starts the
                           pipeline in the background, and answers right away
                           with 202 + the ticket_id.
  GET  /rfp/tickets        list of tickets, newest first (for the UI table).
  GET  /rfp/tickets/{id}   one ticket: status, metadata, key aspects, the
                           Sales summary and (Part 2) the drafts. The UI polls
                           this one.

Part 2 (response generation):
  POST /rfp/tickets/{id}/generate   start the draft for every department of a
                           ticket that finished intake. Answers 202 at once.

No agent logic lives here. This file only calls run_intake() and
run_response() and saves what they return.

Part 2 starts from what Part 1 SAVED (the ticket, its metadata and each
department's key aspects and open questions). The PDF is never read again.

The ticket's status follows the work in real time:
    intake_complete -> drafting -> under_evaluation -> needs_human_review
                                                    \\-> (stays under_evaluation
                                                         when every section passed)
Each department's row also says what it is doing right now (evaluation_results
has section_status "running", plus the stage and the draft number).

A ticket can never stay stuck:
  - Part 1: a failed or crashed intake becomes "failed"
  - Part 2: a failed or crashed generation goes back to "intake_complete" with
    an error_message, so the user can simply try again
  - a server restart mid-run is cleaned up by fail_interrupted_tickets()
    (called from main.py at startup)
"""

import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

import database
from database import get_db
from dependencies import get_current_user
from rfp_models import (
    DepartmentSection,
    RfpMetadata,
    RfpTicket,
    STATUS_ANALYZING,
    STATUS_DISCARDED,
    STATUS_DRAFTING,
    STATUS_FAILED,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
)

# data/pipelines/ isn't an installable package -- same hand-rolled sys.path
# pattern as routes/knowledge.py and celery_app.py.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake.graph import run_intake  # noqa: E402  (data/pipelines/rfp_intake/graph.py)
from rfp_response.graph import run_response  # noqa: E402  (data/pipelines/rfp_response/graph.py)
import rfp_trace  # noqa: E402  (data/pipelines/rfp_trace.py)
from rfp_trace_store import store_event  # noqa: E402  (services/api/rfp_trace_store.py)

UPLOAD_DIR = REPO_ROOT / "data" / "raw" / "rfp_uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# A section is finished when its evaluation_results says so (Part 2).
SECTION_DONE = ("passed", STATUS_NEEDS_HUMAN_REVIEW)
# Tickets that drafts can be (re)generated for. A ticket whose drafts are being
# written right now is refused separately (see _generation_running).
CAN_GENERATE = (STATUS_INTAKE_COMPLETE, STATUS_UNDER_EVALUATION, STATUS_NEEDS_HUMAN_REVIEW)

router = APIRouter(prefix="/rfp", tags=["rfp"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stored_path(path: Path) -> str:
    """Save paths relative to the repo, so they still work on another machine."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _pdf_location(stored: str) -> Path:
    path = Path(stored)
    return path if path.is_absolute() else REPO_ROOT / path


# ---------------------------------------------------------------------------
# Part 1: intake, background work
# ---------------------------------------------------------------------------

def _save_result(db: Session, ticket: RfpTicket, state: dict) -> None:
    """Write everything run_intake() found into Supabase."""
    status = state.get("status", STATUS_FAILED)
    meta = state.get("metadata") or {}
    readability = state.get("readability") or {}

    # The convert step worked, so we at least have language + readability.
    if readability:
        db.add(RfpMetadata(
            ticket_id=ticket.id,
            client_name=meta.get("client_name"),
            location=meta.get("location"),
            service_type=meta.get("service_type"),
            scope=meta.get("scope"),
            deadline=meta.get("deadline"),
            budget_range=meta.get("budget_range"),
            language=state.get("language"),
            departments_needed=state.get("departments_needed") or [],
            missing_fields=state.get("missing_fields") or [],
            word_count=readability.get("word_count"),
            flesch_kincaid=readability.get("flesch_kincaid"),
            gunning_fog=readability.get("gunning_fog"),
            readability_note=readability.get("readability_note"),
        ))

    # Key aspects are only saved for a fully finished run, never half of one.
    if status == STATUS_INTAKE_COMPLETE:
        for department_id, section in (state.get("sections") or {}).items():
            db.add(DepartmentSection(
                ticket_id=ticket.id,
                department_id=department_id,
                key_aspects=section.get("key_aspects") or [],
                open_questions=section.get("open_questions") or [],
            ))
        ticket.sales_summary = state.get("sales_summary")

    ticket.rfp_id = meta.get("rfp_id")
    ticket.discard_reason = state.get("discard_reason") if status == STATUS_DISCARDED else None
    ticket.error_message = state.get("error") if status == STATUS_FAILED else None
    ticket.status = status
    ticket.updated_at = _now()
    db.add(ticket)
    db.commit()


def _mark_failed(ticket_id: int, message: str) -> None:
    try:
        with Session(database.engine) as db:
            ticket = db.get(RfpTicket, ticket_id)
            if ticket is not None:
                ticket.status = STATUS_FAILED
                ticket.error_message = message
                ticket.updated_at = _now()
                db.add(ticket)
                db.commit()
    except Exception as error:  # nothing left to try: at least say so in the log
        print(f"RFP ticket {ticket_id}: could not even mark it failed ({error})")


def process_ticket(ticket_id: int) -> None:
    """Runs in the background after the upload has already been answered.

    Opens its OWN database session: the request's session (get_db) is closed
    by the time this runs.
    """
    try:
        with Session(database.engine) as db:
            ticket = db.get(RfpTicket, ticket_id)
            if ticket is None:
                return
            with rfp_trace.tracing(ticket_id, 1, "intake", store_event):
                state = run_intake(_pdf_location(ticket.raw_pdf_path), ticket_id=ticket_id)
            _save_result(db, ticket, state)
    except Exception as error:
        _mark_failed(ticket_id, f"could not process ticket: {type(error).__name__}: {error}")


# ---------------------------------------------------------------------------
# Part 2: response generation, helpers
# ---------------------------------------------------------------------------

def _section_finished(section: DepartmentSection) -> bool:
    return (section.evaluation_results or {}).get("section_status") in SECTION_DONE


def _generation_running(ticket: RfpTicket, sections: list) -> bool:
    """True while drafts are being written or evaluated.

    "drafting" is always a run in progress. "under_evaluation" is either a run
    in progress (some section is not finished) or a finished run where every
    section passed and the ticket now waits for Part 3.
    """
    if ticket.status == STATUS_DRAFTING:
        return True
    return ticket.status == STATUS_UNDER_EVALUATION and any(
        not _section_finished(s) for s in sections
    )


def _clear_generation(db: Session, ticket: RfpTicket, sections: list, message: str) -> None:
    """Put a ticket back to intake_complete, throwing away unfinished drafts."""
    for section in sections:
        section.draft_content = None
        section.evaluation_results = None
        db.add(section)
    ticket.status = STATUS_INTAKE_COMPLETE
    ticket.error_message = message
    ticket.updated_at = _now()
    db.add(ticket)


def _revert_generation(ticket_id: int, message: str) -> None:
    try:
        with Session(database.engine) as db:
            ticket = db.get(RfpTicket, ticket_id)
            if ticket is None:
                return
            sections = db.exec(
                select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)
            ).all()
            _clear_generation(db, ticket, sections, message)
            db.commit()
    except Exception as error:  # nothing left to try: at least say so in the log
        print(f"RFP ticket {ticket_id}: could not undo a failed generation ({error})")


def _load_handoff(db: Session, ticket: RfpTicket) -> tuple[dict, dict]:
    """Part 1's handoff: the ticket's metadata and each department's key aspects
    and open questions, read from the database. The PDF is not read."""
    meta = db.exec(select(RfpMetadata).where(RfpMetadata.ticket_id == ticket.id)).first()
    sections = db.exec(
        select(DepartmentSection).where(DepartmentSection.ticket_id == ticket.id)
    ).all()

    metadata = {"rfp_id": ticket.rfp_id}
    if meta is not None:
        for field in ("client_name", "location", "service_type", "scope", "deadline", "budget_range"):
            metadata[field] = getattr(meta, field)
    inputs = {
        s.department_id: {
            "key_aspects": list(s.key_aspects or []),
            "open_questions": list(s.open_questions or []),
        }
        for s in sections
    }
    return metadata, inputs


def _record_progress(ticket_id: int, department_id: str, stage: str, iteration: int) -> None:
    """Called by the pipeline as each department moves along. Makes the ticket
    and the department's row show what is happening right now."""
    if stage == "finished":
        return  # the final save writes the finished section
    with Session(database.engine) as db:
        section = db.exec(
            select(DepartmentSection).where(
                DepartmentSection.ticket_id == ticket_id,
                DepartmentSection.department_id == department_id,
            )
        ).first()
        if section is not None:
            section.evaluation_results = {
                "section_status": "running", "stage": stage, "iteration": iteration,
            }
            db.add(section)
        if stage == "evaluating":
            ticket = db.get(RfpTicket, ticket_id)
            if ticket is not None and ticket.status == STATUS_DRAFTING:
                ticket.status = STATUS_UNDER_EVALUATION
                ticket.updated_at = _now()
                db.add(ticket)
        db.commit()


def _evaluation_payload(section: dict) -> dict:
    """What is saved in a section's evaluation_results: the structured
    EvaluationResult from the ticket (department_id, readability, relevance,
    compliance, overall_pass, feedback_for_generator) plus how the loop went."""
    payload = dict(section["evaluation_result"] or {})
    payload.update({
        "department_id": section["department_id"],
        "section_status": section["status"],
        "iterations": section["iterations"],
        "history": section["history"],
        "error": section["error"],
    })
    if section["evaluation_result"] is None:
        payload["overall_pass"] = False  # a section with no evaluation did not pass
    return payload


def _save_generation(db: Session, ticket: RfpTicket, state: dict) -> None:
    sections = {
        s.department_id: s
        for s in db.exec(
            select(DepartmentSection).where(DepartmentSection.ticket_id == ticket.id)
        ).all()
    }
    for department_id, result in state["results"].items():
        row = sections.get(department_id)
        if row is None:
            continue
        row.draft_content = result["draft_content"]
        row.evaluation_results = _evaluation_payload(result)
        db.add(row)
    ticket.status = state["status"]
    ticket.error_message = None
    ticket.updated_at = _now()
    db.add(ticket)


def process_generation(ticket_id: int) -> None:
    """Runs in the background after the generate request has been answered.

    Reads Part 1's saved results, runs one generate / evaluate / revise loop
    per department, and saves every draft with its EvaluationResult. A section
    that never passed keeps its last draft and is marked needs_human_review.
    """
    try:
        with Session(database.engine) as db:
            ticket = db.get(RfpTicket, ticket_id)
            if ticket is None:
                return
            metadata, inputs = _load_handoff(db, ticket)

        with rfp_trace.tracing(ticket_id, 2, "response", store_event) as tracer:
            def progress(department_id, stage, iteration):
                tracer.progress(department_id, stage, iteration)   # one trace event per draft round
                _record_progress(ticket_id, department_id, stage, iteration)

            state = run_response(ticket_id, metadata, inputs, on_progress=progress)
        if state["status"] == STATUS_FAILED:
            _revert_generation(ticket_id, state.get("error") or "Draft generation failed.")
            return

        with Session(database.engine) as db:
            ticket = db.get(RfpTicket, ticket_id)
            _save_generation(db, ticket, state)
            db.commit()
    except Exception as error:
        _revert_generation(ticket_id, f"Draft generation failed: {type(error).__name__}: {error}")


def fail_interrupted_tickets() -> None:
    """Called once at server startup (main.py lifespan).

    Both pipelines run inside this server process. If the server stopped
    mid-run, the tickets would keep saying "analyzing" or "drafting" forever.
    At startup nothing is running yet, so:
      - a ticket still "analyzing" was interrupted and becomes "failed"
      - a ticket that is "drafting", or "under_evaluation" with an unfinished
        section, had its drafts cut off. It goes back to "intake_complete"
        with a message, so the drafts can be generated again.
    A ticket whose sections are all finished is left alone: it is not running,
    it is waiting.
    Does nothing when DATABASE_URL isn't set (same rule as init_inventory_db).
    """
    if database.engine is None:
        return
    try:
        with Session(database.engine) as db:
            analyzing = db.exec(select(RfpTicket).where(RfpTicket.status == STATUS_ANALYZING)).all()
            for ticket in analyzing:
                ticket.status = STATUS_FAILED
                ticket.error_message = "Interrupted: the server restarted while this ticket was being analyzed."
                ticket.updated_at = _now()
                db.add(ticket)

            in_progress = db.exec(
                select(RfpTicket).where(
                    RfpTicket.status.in_([STATUS_DRAFTING, STATUS_UNDER_EVALUATION])
                )
            ).all()
            for ticket in in_progress:
                sections = db.exec(
                    select(DepartmentSection).where(DepartmentSection.ticket_id == ticket.id)
                ).all()
                if _generation_running(ticket, sections):
                    _clear_generation(
                        db, ticket, sections,
                        "Interrupted: the server restarted while the drafts were being generated. "
                        "You can generate them again.",
                    )
            db.commit()
    except Exception as error:  # never stop the whole API from booting over this
        print(f"Could not check for interrupted RFP tickets: {error}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/tickets", status_code=202)
async def upload_rfp(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    name = file.filename or "upload.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The PDF is too large (limit: 10 MB).")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That file is empty or is not a real PDF.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved = UPLOAD_DIR / f"{uuid.uuid4().hex}.pdf"
    saved.write_bytes(content)

    ticket = RfpTicket(original_filename=name, raw_pdf_path=_stored_path(saved))
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    background_tasks.add_task(process_ticket, ticket.id)
    return {"ticket_id": ticket.id, "status": ticket.status}


@router.post("/tickets/{ticket_id}/generate", status_code=202)
def generate_drafts(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    ticket = db.get(RfpTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    sections = db.exec(
        select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)
    ).all()
    if _generation_running(ticket, sections):
        raise HTTPException(status_code=409, detail="Drafts are already being generated for this ticket.")
    if ticket.status not in CAN_GENERATE or not sections:
        raise HTTPException(
            status_code=409,
            detail=f"Drafts can only be generated for a ticket that finished intake (this one is '{ticket.status}').",
        )

    # Every department starts again from a clean "queued" row. From this moment
    # the ticket counts as running, so a second request is refused.
    for section in sections:
        section.draft_content = None
        section.evaluation_results = {"section_status": "running", "stage": "queued", "iteration": 0}
        db.add(section)
    ticket.status = STATUS_DRAFTING
    ticket.error_message = None
    ticket.updated_at = _now()
    db.add(ticket)
    db.commit()

    background_tasks.add_task(process_generation, ticket_id)
    return {"ticket_id": ticket_id, "status": STATUS_DRAFTING}


@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    tickets = db.exec(select(RfpTicket).order_by(RfpTicket.created_at.desc())).all()
    metadata = {m.ticket_id: m for m in db.exec(select(RfpMetadata)).all()}
    sections_by_ticket = defaultdict(list)
    for section in db.exec(select(DepartmentSection)).all():
        sections_by_ticket[section.ticket_id].append(section)
    return [
        {
            "ticket_id": t.id,
            "status": t.status,
            "original_filename": t.original_filename,
            "client_name": metadata[t.id].client_name if t.id in metadata else None,
            "departments_needed": metadata[t.id].departments_needed if t.id in metadata else [],
            "generation_running": _generation_running(t, sections_by_ticket[t.id]),
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in tickets
    ]


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    ticket = db.get(RfpTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    metadata = db.exec(select(RfpMetadata).where(RfpMetadata.ticket_id == ticket_id)).first()
    sections = sorted(
        db.exec(select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)).all(),
        key=lambda s: s.id,
    )
    finished = [s.evaluation_results["iterations"] for s in sections if _section_finished(s)]

    return {
        "ticket_id": ticket.id,
        "status": ticket.status,
        "original_filename": ticket.original_filename,
        "rfp_id": ticket.rfp_id,
        "discard_reason": ticket.discard_reason,
        "error_message": ticket.error_message,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "metadata": metadata.model_dump(exclude={"id", "ticket_id"}) if metadata else None,
        "sales_summary": ticket.sales_summary,
        "generation_running": _generation_running(ticket, sections),
        "average_iterations": round(sum(finished) / len(finished), 2) if finished else None,
        "sections": [
            {
                "department_id": s.department_id,
                "key_aspects": s.key_aspects,
                "open_questions": s.open_questions,
                "approval_status": s.approval_status,
                "draft_content": s.draft_content,
                "evaluation_results": s.evaluation_results,
            }
            for s in sections
        ],
    }
