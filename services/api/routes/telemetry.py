"""
routes/telemetry.py -- stub telemetry ingestion endpoint.

Phase 2 (Capture) of the telemetry unit: this endpoint exists only to
verify the frontend's TelemetryService is producing correctly-shaped
batches. It validates each event against the TelemetryEvent contract
and returns a count -- nothing is persisted here. Phase 3 (Storage)
replaces the body of this function with the real Supabase-backed
implementation, reusing TelemetryEvent unchanged.

No auth dependency on purpose: user_login_failed fires before a JWT
exists, so this endpoint has to accept events from a not-yet-
authenticated session.

Events are parsed one at a time with model_validate() rather than
typing the whole request body as list[TelemetryEvent]. A typed body
would mean one malformed event fails the ENTIRE batch with a 422.
Per-event parsing means one bad event doesn't take down the rest --
which matters once Phase 3 actually persists the valid ones. Building
that pattern now, even though this stub discards every event either
way, means Phase 3 is a swap of what happens to a valid event, not a
rewrite of how events get parsed.
"""

import json
import os

from fastapi import APIRouter, Request
from pydantic import ValidationError

from telemetry_schemas import TelemetryEvent

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Not read anywhere yet -- this endpoint's own URL doesn't change based
# on it today. Declared now per the brief, so the pattern already
# exists by the time Phase 3 needs it.
TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT")


@router.post("/events")
async def receive_events(request: Request):
    # Reads the raw body directly instead of declaring a `dict`
    # parameter -- FastAPI gates that kind of parameter on the
    # Content-Type header actually being application/json. sendBeacon()
    # can't reliably send that header cross-origin (application/json
    # isn't CORS-safelisted, and sendBeacon doesn't handle a required
    # preflight the way fetch does -- see lib/telemetry.ts's
    # flushWithBeacon), so it sends the same JSON body labeled
    # text/plain instead. This endpoint has to accept that regardless
    # of the declared Content-Type, or the one delivery path meant to
    # survive a closing tab would be the one path that never works.
    raw_body = await request.body()
    try:
        parsed = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"received": 0}

    raw_events = parsed.get("events", []) if isinstance(parsed, dict) else []
    received = len(raw_events)
    event_types: list[str] = []

    for raw in raw_events:
        try:
            event = TelemetryEvent.model_validate(raw)
        except ValidationError:
            # Phase 3 will count and report these as "rejected" instead
            # of silently skipping them. This stub only needs to prove
            # the batch shape and event types are arriving correctly.
            continue
        event_types.append(event.event_type)

    print(f"[telemetry stub] received {received} event(s): {event_types}")
    return {"received": received}