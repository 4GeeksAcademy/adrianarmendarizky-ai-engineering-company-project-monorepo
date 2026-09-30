"""
routes/rfp.py -- the HTTP side of the RFP intake workflow (Milestone 9, Part 1).

Three endpoints, all behind login (same get_current_user as /inventory):
  POST /rfp/tickets        upload one PDF. Saves it under data/raw/rfp_uploads/,
                           creates the ticket as "analyzing", starts the
                           pipeline in the background, and answers right away
                           with 202 + the ticket_id.
  GET  /rfp/tickets        list of tickets, newest first (for the UI table).
  GET  /rfp/tickets/{id}   one ticket: status, metadata, key aspects, and the
                           Sales summary. The UI polls this one.

No agent logic lives here. This file only calls run_intake() from
data/pipelines/rfp_intake/graph.py and saves what it returns.

A ticket can never stay stuck on "analyzing":
  - if the pipeline returns an error, the ticket becomes "failed"
  - if saving the results crashes, the ticket becomes "failed"
  - if the whole server restarts mid-run, fail_interrupted_tickets()
    (called from main.py at startup) marks those tickets "failed"
"""

import sys
import uuid
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
    STATUS_FAILED,
    STATUS_INTAKE_COMPLETE,
)

# data/pipelines/ isn't an installable package -- same hand-rolled sys.path
# pattern as routes/knowledge.py and celery_app.py.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from rfp_intake.graph import run_intake  # noqa: E402  (data/pipelines/rfp_intake/graph.py)

UPLOAD_DIR = REPO_ROOT / "data" / "raw" / "rfp_uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

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
# Background work
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
            state = run_intake(_pdf_location(ticket.raw_pdf_path), ticket_id=ticket_id)
            _save_result(db, ticket, state)
    except Exception as error:
        _mark_failed(ticket_id, f"could not process ticket: {type(error).__name__}: {error}")


def fail_interrupted_tickets() -> None:
    """Called once at server startup (main.py lifespan).

    The pipeline runs inside this server process. If the server stopped
    mid-run, those tickets would say "analyzing" forever. At startup nothing
    is running yet, so any ticket still "analyzing" was interrupted.
    Does nothing when DATABASE_URL isn't set (same rule as init_inventory_db).
    """
    if database.engine is None:
        return
    try:
        with Session(database.engine) as db:
            stuck = db.exec(select(RfpTicket).where(RfpTicket.status == STATUS_ANALYZING)).all()
            for ticket in stuck:
                ticket.status = STATUS_FAILED
                ticket.error_message = "Interrupted: the server restarted while this ticket was being analyzed."
                ticket.updated_at = _now()
                db.add(ticket)
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


@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    tickets = db.exec(select(RfpTicket).order_by(RfpTicket.created_at.desc())).all()
    metadata = {m.ticket_id: m for m in db.exec(select(RfpMetadata)).all()}
    return [
        {
            "ticket_id": t.id,
            "status": t.status,
            "original_filename": t.original_filename,
            "client_name": metadata[t.id].client_name if t.id in metadata else None,
            "departments_needed": metadata[t.id].departments_needed if t.id in metadata else [],
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
    sections = db.exec(
        select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)
    ).all()

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
        "sections": [
            {
                "department_id": s.department_id,
                "key_aspects": s.key_aspects,
                "open_questions": s.open_questions,
                "approval_status": s.approval_status,
            }
            for s in sorted(sections, key=lambda s: s.id)
        ],
    }
