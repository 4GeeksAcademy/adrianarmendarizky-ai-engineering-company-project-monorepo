"""
rfp_notify.py -- sends the live "new RFP ticket" notification (Real-Time
Systems, Part 1).

It fires when the intake graph's "orchestrate" step finishes: by then the
classifier accepted the document as an RFP, the extracted details (client,
location, service type) exist, and the ticket is still "analyzing". A document
the classifier rejects never reaches that step, so it never notifies.

The pipeline already reports every step as a trace event saved in rfp_events.
store_and_notify() is the sink for those events: it saves each one exactly as
before and, for the orchestrate step, also publishes the notification. The
reconnect replay (routes/rfp_events.py) reads the same saved events, so a live
notification and a replayed one are built by the same code.
"""

from sqlmodel import Session, select

import database
from rfp_models import STATUS_ANALYZING, RfpEvent, RfpTicket
from rfp_trace_store import store_event
from sse_broker import broker

NOTIFY_AGENT = "intake:orchestrate"
NOTIFY_EVENT_TYPE = "node_finished"


def event_message(db: Session, row: RfpEvent) -> dict:
    """One notification, built from one saved orchestrate event.

    "id" is the saved event's own row number: it only ever goes up, in the
    order notifications were sent, so it is what the browser sends back as
    Last-Event-ID. "data" is the JSON body (ticket fields only).
    """
    ticket = db.get(RfpTicket, row.ticket_id)
    meta = (row.output_data or {}).get("metadata") or {}
    created = ticket.created_at if ticket is not None else row.created_at
    created_iso = created.isoformat()
    if created.tzinfo is None:
        created_iso += "Z"
    return {
        "id": row.id,
        "data": {
            "ticket_id": row.ticket_id,
            "rfp_id": meta.get("rfp_id"),
            "client_name": meta.get("client_name"),
            "location": meta.get("location"),
            "service_type": meta.get("service_type"),
            "status": STATUS_ANALYZING,
            "created_at": created_iso,
        },
    }


def store_and_notify(event: dict) -> None:
    """The trace sink for intake: save the event, then notify if it is the one."""
    store_event(event)
    if event.get("agent") != NOTIFY_AGENT or event.get("event_type") != NOTIFY_EVENT_TYPE:
        return
    try:
        with Session(database.engine) as db:
            row = db.exec(
                select(RfpEvent)
                .where(RfpEvent.ticket_id == event["ticket_id"])
                .where(RfpEvent.agent == NOTIFY_AGENT)
                .where(RfpEvent.event_type == NOTIFY_EVENT_TYPE)
                .order_by(RfpEvent.id.desc())
            ).first()
            if row is None:
                return
            message = event_message(db, row)
        broker.publish(message)
    except Exception as error:  # a failed notification never stops the pipeline
        print(f"RFP notification: could not send it ({error})")
