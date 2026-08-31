"""
routes/telemetry.py -- telemetry ingestion + reporting endpoints.

POST /telemetry/events (Phase 3: Storage) persists events. The URL and
response shape are compatible with what the frontend already expects
(it only reads the HTTP status code -- see lib/telemetry.ts's
sendBatch), so uis/backoffice needed no changes for that swap.

No auth dependency on that endpoint, on purpose: user_login_failed
fires before a JWT exists, so it has to accept events from a
not-yet-authenticated session.

Events are parsed one at a time with model_validate() rather than
typing the whole request body as list[TelemetryEvent]. A typed body
would mean one malformed event fails the ENTIRE batch with a 422
before the function even runs, cancelling every valid event alongside
it. Per-event parsing is what makes "reject individually, persist the
rest" possible.

The raw body is read directly with request.body(), not a `dict`
FastAPI parameter -- sendBeacon() (used by the frontend on tab-close)
sends its payload as Content-Type: text/plain, not application/json,
since application/json isn't CORS-safelisted and sendBeacon can't
complete a cross-origin preflight the way fetch does. A `dict`
parameter would reject that request outright regardless of body
content. See lib/telemetry.ts's flushWithBeacon for the frontend side
of this.

GET /telemetry/report (Phase 4: Report) is new. It resolves a
start_date/end_date window (defaulting to the last 7 days), calls
every metric function in telemetry_analysis.py with that window, and
returns them together under one JSON body. The pipeline itself never
runs inside this function on every request -- it's a thin caller, per
the brief's "don't calculate anything inside the endpoint" rule. A
60-second in-memory cache, keyed by the exact (start, end) pair
requested, is what actually enforces that.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlmodel import Session

import telemetry_analysis
from database import get_db
from telemetry_models import TelemetryEventRecord
from telemetry_schemas import TelemetryEvent

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Not read anywhere yet -- this endpoint's own URL didn't change
# between Phase 2 and this phase. Declared per the brief, establishing
# the pattern from the start.
TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT")

REPORT_CACHE_TTL_SECONDS = 60
# Keyed by the exact (start_date, end_date) ISO strings requested --
# two different windows are two different cache entries, on purpose,
# not one global "the report" slot. A module-level dict is enough for
# a single-process dev/demo deployment; a real production system with
# multiple workers would need a shared cache (Redis, etc.), but
# nothing here claims to be that.
_report_cache: dict[tuple[str, str], tuple[dict, float]] = {}


def _parse_timestamp(raw: str) -> datetime:
    # ISO 8601 strings from the frontend end in "Z" for UTC --
    # fromisoformat wants "+00:00" instead on the Python versions this
    # service targets, so normalize explicitly rather than relying on
    # a specific Python patch version's more lenient parsing.
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _parse_query_datetime(raw: str) -> datetime:
    # Same normalization as _parse_timestamp, plus: a bare date like
    # "2026-08-24" (no time component) parses to a naive datetime.
    # Every other timestamp in this system is UTC-aware, and comparing
    # naive to aware datetimes raises -- so a query param with no
    # explicit timezone is assumed UTC, matching the rest of the
    # contract instead of silently doing the wrong thing.
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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


@router.get("/report")
def get_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    end = _parse_query_datetime(end_date) if end_date else datetime.now(timezone.utc)
    start = _parse_query_datetime(start_date) if start_date else end - timedelta(days=7)

    cache_key = (start.isoformat(), end.isoformat())
    cached = _report_cache.get(cache_key)
    if cached is not None:
        cached_result, cached_at = cached
        if time.monotonic() - cached_at < REPORT_CACHE_TTL_SECONDS:
            return cached_result

    # Every metric function gets the SAME resolved (start, end) -- they
    # never apply their own default window. Resolving it once, here, is
    # what "the endpoint decides the default period" means in practice.
    metrics = {
        "events_per_day": telemetry_analysis.events_per_day(db, start, end),
        "events_by_type_per_day": telemetry_analysis.events_by_type_per_day(db, start, end),
        "api_error_rate_by_day": telemetry_analysis.api_error_rate_per_day(db, start, end),
        "api_latency_avg_ms_by_day": telemetry_analysis.api_latency_avg_ms_per_day(
            db, start, end
        ),
        "auth_failure_rate_by_day": telemetry_analysis.auth_failure_rate_per_day(
            db, start, end
        ),
    }
    result = {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "metrics": metrics,
    }

    _report_cache[cache_key] = (result, time.monotonic())
    return result
