"""
telemetry_schemas.py -- the TelemetryEvent envelope contract.

Mirrors docs/telemetry/telemetry-plan.md Section 1 exactly. Field
names use the same camelCase the frontend TelemetryService produces
(eventId, sessionId, schemaVersion, requestId) rather than this
codebase's usual snake_case Python convention -- the envelope's wire
format IS the contract shared with the frontend, and translating it
back and forth would just be one more place field names could quietly
drift apart. event_type and properties stay as specified in the plan.

Defined once here and reused unchanged by Phase 3 (Storage) -- see the
plan for why that matters: a wrong field name would otherwise need
fixing in two places instead of one.
"""

from typing import Optional

from pydantic import BaseModel


class TelemetryEvent(BaseModel):
    eventId: str
    timestamp: str
    sessionId: str
    userId: Optional[str] = None
    event_type: str
    schemaVersion: int
    requestId: Optional[str] = None
    properties: dict = {}
