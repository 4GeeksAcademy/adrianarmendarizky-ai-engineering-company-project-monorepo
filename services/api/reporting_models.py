"""
reporting_models.py -- SQLModel ORM classes for the `reporting` schema.

Named to match inventory_models.py / telemetry_models.py's convention.
Two tables here, both introduced by the Weekly Location Cost & Waste
Report pipeline (data/pipelines/pipeline.py) -- see PIPELINE_DESIGN.md:

  - WeeklyLocationPerformance: the business-facing KPI table. Schema is
    exactly what CONTEXT-brasaland.md section 5 specifies -- same table
    name, same columns, same unique constraint.
  - PipelineRun: the execution log from PIPELINE_DESIGN.md's "Execution
    log" section -- one row per run of weekly_location_performance_flow,
    written the moment a run starts (status="Running") and updated when
    it finishes, so a run's own row always exists even if the run never
    completes (see PIPELINE_DESIGN.md's Observability §1, "silence vs.
    true absence").

Both tables live under the `reporting` Postgres schema, never `public` --
CONTEXT-brasaland.md section 7 is explicit that this pipeline reads
telemetry_events read-only and never writes into it; keeping its own
output under a separate schema is the same idea applied to where it
writes. database.py's init_inventory_db() creates the `reporting` schema
itself before create_all() runs, since create_all() only ever creates
tables, never schemas -- these are the first tables in this codebase to
need one.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class WeeklyLocationPerformance(SQLModel, table=True):
    __tablename__ = "weekly_location_performance"
    __table_args__ = (
        # This is the constraint the pipeline's upsert (data/pipelines/
        # pipeline.py's load_weekly_performance) relies on for
        # idempotency -- ON CONFLICT (location_id, week_start) DO UPDATE.
        UniqueConstraint("location_id", "week_start", name="uq_location_week"),
        {"schema": "reporting"},
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    location_id: str
    country: str
    week_start: date
    total_purchase_cost: float = 0
    total_waste_cost: float = 0
    waste_ratio: float = 0
    stockout_events_count: int = 0
    price_alert_events_count: int = 0
    currency: str
    computed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    )


class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"
    __table_args__ = {"schema": "reporting"}

    run_id: str = Field(primary_key=True)
    week_start: date
    # "schedule" | "manual" -- which of the two triggers started this run.
    # Needed for the concurrent-runs guard and for GET
    # /reporting/pipeline-runs/latest to answer "did someone force this."
    triggered_by: str
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    # Null while the run is in progress -- a started_at with no
    # completed_at after an unreasonably long time is itself the
    # "stuck or crashed" signal (PIPELINE_DESIGN.md's Observability §1).
    completed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    status: str = "Running"  # "Running" | "Completed" | "Failed"
    records_processed: Optional[int] = None
    locations_written: Optional[int] = None
    error_message: Optional[str] = None
