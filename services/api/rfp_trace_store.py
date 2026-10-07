"""
rfp_trace_store.py -- saves trace events in the rfp_events table (Milestone 9, Part 3).

Every part of the RFP workflow reports what it did as small event dicts (see
data/pipelines/rfp_trace.py for Parts 1 and 2, and data/pipelines/rfp_approval/
tracing.py for Part 3). This is the one place that writes them to the database,
so one ticket has one trace, in order, from the PDF to the final document.

Each event is saved in its own short session, so a slow or failed save never
holds up the pipeline (the callers catch the error and carry on).
"""

from datetime import datetime, timezone

from sqlmodel import Session

import database
from rfp_models import RfpEvent


def _when(value) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def store_event(event: dict) -> None:
    """Save one trace event. Events with no ticket are ignored."""
    if event.get("ticket_id") is None:
        return
    with Session(database.engine) as db:
        db.add(RfpEvent(
            ticket_id=event["ticket_id"], part=event["part"], agent=event["agent"],
            event_type=event["event_type"], subject=event.get("subject"),
            input_data=event.get("input"), output_data=event.get("output"),
            actor=event.get("actor"), created_at=_when(event.get("timestamp")),
        ))
        db.commit()
