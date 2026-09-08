"""
job_runs_models.py -- SQLModel ORM class for the nightly export / job
orchestration control table.

Named to match inventory_models.py / telemetry_models.py /
reporting_models.py's convention -- one file per feature area.

job_runs is a different layer than reporting.pipeline_runs (see
reporting_models.py): pipeline_runs is Milestone 6's own execution log,
one row per weekly_location_performance_flow run. job_runs is this
project's nightly orchestration log -- one row per attempt to run
scripts/nightly_export.py for a given (job_name, target_date). Similar
shape (both track Running/Completed/Failed), different process --
never merged.

Lives in the default `public` schema, not `reporting` -- job_runs
isn't specific to the reporting pipeline (a future job could reuse
this same table), so it doesn't belong under a schema named for one
pipeline. telemetry_events makes the same public-schema call for the
same reason.

No unique constraint on (job_name, target_date) on purpose: a failed
attempt and a later retry for the same day are both real rows worth
keeping, not something to upsert away. The plain index below only
exists to make the two idempotency checks
(scripts/nightly_export.py's "is there already a processing row" /
"is there already a completed row for this day") fast -- it doesn't
enforce anything on its own.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Index
from sqlmodel import Field, SQLModel


class JobRun(SQLModel, table=True):
    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_job_name_target_date", "job_name", "target_date"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    job_name: str
    target_date: date
    # "pending" | "processing" | "completed" | "failed" -- "processing"
    # doubles as the distributed lock (see scripts/nightly_export.py).
    # No row should remain "processing" after the script exits, success
    # or failure -- that's what the try/except/finally there guarantees.
    status: str = "pending"
    error_message: Optional[str] = None
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    )