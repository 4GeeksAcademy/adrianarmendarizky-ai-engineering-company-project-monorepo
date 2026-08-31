"""
telemetry_models.py -- SQLModel ORM class for the telemetry_events table.

Named to match inventory_models.py's convention. Maps directly to
Supabase (Postgres), same as the inventory tables -- nothing here
talks to TinyDB.

Eight columns, one for each TelemetryEvent envelope field
(telemetry_schemas.py) -- properties is the only rename, to tags,
since that's the column the GIN index below targets. event_id is the
client-generated UUID from the envelope, already guaranteed unique
per event, so it IS the primary key rather than a separate serial id.

This table is write-only by design: events are immutable facts once
recorded (see docs/telemetry/telemetry-plan.md). No route in this
codebase issues an UPDATE or DELETE against it, and none should be
added -- if a future requirement needs to correct bad data, that's a
new event, not an edit to an old one.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class TelemetryEventRecord(SQLModel, table=True):
    __tablename__ = "telemetry_events"

    event_id: str = Field(primary_key=True)
    # timezone=True -> TIMESTAMPTZ, not the driver's default TIMESTAMP
    # WITHOUT TIME ZONE. Every timestamp in this system is UTC (the
    # envelope's own contract) -- the column should enforce that, not
    # silently assume it.
    timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True), index=True, nullable=False)
    )
    session_id: str
    user_id: Optional[str] = None
    event_type: str = Field(index=True)
    schema_version: int
    request_id: Optional[str] = None
    # JSONB, not a plain string column -- stores TelemetryEvent.properties
    # unchanged (allowlisted keys only, per the approved plan). The GIN
    # index below is what makes searching inside this column fast at
    # scale -- see docs/telemetry/telemetry-plan.md and the brief's
    # "why bulk insert / GIN matters" section.
    tags: dict = Field(sa_column=Column(JSONB))

    __table_args__ = (
        Index("ix_telemetry_events_tags_gin", "tags", postgresql_using="gin"),
    )
