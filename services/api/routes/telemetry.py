"""
routes/telemetry.py -- telemetry ingestion endpoint (Phase 3: Storage).

Replaces Phase 2's stub. The URL and response shape are compatible
with what the frontend already expects (it only reads the HTTP status
code -- see lib/telemetry.ts's sendBatch), so uis/backoffice needs no
changes for this swap. What changes is entirely inside this function:
valid events are now actually persisted, in a single bulk insert per
batch, instead of being counted and discarded.

No auth dependency on purpose: user_login_failed fires before a JWT
exists, so this endpoint has to accept events from a not-yet-
authenticated session.

Events are still parsed one at a time with model_validate(), same as
the stub, and for the same reason: a typed list[TelemetryEvent] body
would mean one malformed event fails the ENTIRE batch with a 422
before this function even runs, cancelling every valid event alongside
it. Per-event parsing is what makes "reject individually, persist the
rest" possible at all.

The raw body is still read directly with request.body(), not a `dict`
FastAPI parameter -- sendBeacon() (used by the frontend on tab-close)
sends its payload as Content-Type: text/plain, not application/json,
since application/json isn't CORS-safelisted and sendBeacon can't
complete a cross-origin preflight the way fetch does. A `dict`
parameter would reject that request outright regardless of body
content. See lib/telemetry.ts's flushWithBeacon for the frontend side
of this.
"""

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlmodel import Session

from database import get_db
from telemetry_models import TelemetryEventRecord
from telemetry_schemas import TelemetryEvent

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Not read anywhere yet -- this endpoint's own URL didn't change
# between Phase 2 and this phase. Declared per the brief, establishing
# the pattern from the start.
TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT")


def _parse_timestamp(raw: str) -> datetime:
    # ISO 8601 strings from the frontend end in "Z" for UTC --
    # fromisoformat wants "+00:00" instead on the Python versions this
    # service targets, so normalize explicitly rather than relying on
    # a specific Python patch version's more lenient parsing.
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@router.post("/events")
async def receive_events(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    try:
        parsed = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"received": 0, "stored": 0, "rejected": 0}

    raw_events = parsed.get("events", []) if isinstance(parsed, dict) else []
    received = len(raw_events)

    records: list[TelemetryEventRecord] = []
    rejected = 0

    for raw in raw_events:
        try:
            event = TelemetryEvent.model_validate(raw)
        except ValidationError:
            rejected += 1
            continue
        try:
            records.append(
                TelemetryEventRecord(
                    event_id=event.eventId,
                    timestamp=_parse_timestamp(event.timestamp),
                    session_id=event.sessionId,
                    user_id=event.userId,
                    event_type=event.event_type,
                    schema_version=event.schemaVersion,
                    request_id=event.requestId,
                    tags=event.properties,
                )
            )
        except (ValueError, TypeError):
            # A well-formed envelope with an unparseable timestamp
            # string is still a rejected event, not a 500 for the
            # whole batch.
            rejected += 1

    # The whole point: one INSERT statement covering every valid
    # record in this batch, in one transaction -- not one INSERT (and
    # one transaction) per event. See docs/telemetry/telemetry-plan.md
    # and the brief's "why bulk insert matters" section for why that
    # distinction is the difference between this holding up in
    # production and collapsing the connection pool under real load.
    stored = 0
    if records:
        db.add_all(records)
        db.commit()
        stored = len(records)

    print(f"[telemetry] received {received}, stored {stored}, rejected {rejected}")
    return {"received": received, "stored": stored, "rejected": rejected}