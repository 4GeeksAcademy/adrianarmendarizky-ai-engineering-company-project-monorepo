"""
routes/rfp_events.py -- live "new RFP ticket" notifications over SSE
(Real-Time Systems, Part 1).

  GET /rfp/events    a stream that stays open. Each time a ticket is
                     registered the server sends:

                         id: 42
                         event: rfp_ticket_created
                         data: {"ticket_id": 42, "status": "analyzing", ...}

Behind login (same get_current_user as the rest of the API). The browser
must send the token in an Authorization header, so it uses fetch, not
the bare EventSource.

If the connection drops, the browser reconnects and sends the id of the
last event it saw in the Last-Event-ID header. The server then looks in
the database for tickets newer than that id and sends them first, so
nothing registered while the client was offline is lost.

No model or agent calls live here. This is only a communication layer.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

import database
from dependencies import get_current_user
from rfp_models import STATUS_ANALYZING, RfpTicket
from sse_broker import broker

router = APIRouter(prefix="/rfp", tags=["rfp-events"])

EVENT_NAME = "rfp_ticket_created"
KEEPALIVE_SECONDS = 15
MAX_REPLAY = 100


def _sse_message(data: dict) -> str:
    """One SSE message: id + named event + JSON data, ended by a blank line."""
    return f"id: {data['ticket_id']}\nevent: {EVENT_NAME}\ndata: {json.dumps(data)}\n\n"


def _missed_tickets(last_id: int) -> list[dict]:
    """Tickets registered after last_id, oldest first (for a reconnecting client)."""
    with Session(database.engine) as db:
        rows = db.exec(
            select(RfpTicket)
            .where(RfpTicket.id > last_id)
            .order_by(RfpTicket.id)
            .limit(MAX_REPLAY)
        ).all()
        return [
            {
                "ticket_id": row.id,
                "status": STATUS_ANALYZING,  # the status a ticket has when it is created
                "original_filename": row.original_filename,
            }
            for row in rows
        ]


async def _event_stream(request: Request, last_id: Optional[int]):
    # Sign up for live messages FIRST, then look for missed ones. This way a
    # ticket registered during the lookup is not lost.
    queue = broker.subscribe()
    try:
        yield ": connected\n\n"  # sends the headers right away

        sent_up_to = 0
        if last_id is not None:
            sent_up_to = last_id
            for item in await asyncio.to_thread(_missed_tickets, last_id):
                yield _sse_message(item)
                sent_up_to = item["ticket_id"]

        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # a comment line: keeps the connection open
                continue
            if message["ticket_id"] <= sent_up_to:
                continue  # already sent during the replay -- never show a ticket twice
            sent_up_to = message["ticket_id"]
            yield _sse_message(message)
    finally:
        broker.unsubscribe(queue)


@router.get("/events")
async def rfp_events(
    request: Request,
    last_event_id: Optional[str] = Header(default=None),
    _user=Depends(get_current_user),
):
    try:
        last_id = int(last_event_id) if last_event_id is not None else None
    except ValueError:
        last_id = None

    return StreamingResponse(
        _event_stream(request, last_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
