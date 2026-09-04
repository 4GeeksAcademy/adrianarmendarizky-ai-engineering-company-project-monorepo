"""
routes/reporting.py -- endpoints for the Weekly Location Cost & Waste
Report pipeline.

Kept as its own module, separate from routes/telemetry.py, per
CONTEXT-brasaland.md and PIPELINE_DESIGN.md's "A note on
services/reporting/" -- same reasoning as why telemetry_analysis.py lives
inside services/api/ rather than a new top-level services/telemetry/
directory (see that file's own docstring): a new top-level service would
need its own Dockerfile/compose entry for no benefit, since nothing here
is shared outside this API. So this is services/reporting/ in spirit --
its own file, its own router, its own prefix -- without being a second
deployable service.

No ETL logic lives here. Every route below is a thin caller into
data/pipelines/pipeline.py -- the same rule GET /telemetry/report already
follows for telemetry_analysis.py ("don't calculate anything inside the
endpoint").
"""

import sys
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_db
from reporting_models import PipelineRun, WeeklyLocationPerformance

# data/pipelines/ isn't services/api's own package, so it needs the same
# hand-rolled sys.path treatment already used elsewhere in this repo to
# reach a sibling directory (see scripts/analyze.py,
# app/incidents/controller.py, and data/pipelines/pipeline.py's own
# version of this same pattern in reverse).
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

from pipeline import weekly_location_performance_flow  # noqa: E402

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/weekly-location-performance")
def get_weekly_location_performance(
    week_start: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """KPI query -- reads reporting.weekly_location_performance directly.
    All the computation already happened the last time the pipeline ran;
    this endpoint never triggers a run itself. Defaults to the most
    recently computed week when week_start isn't given. Response shape
    matches CONTEXT-brasaland.md section 6's example exactly.
    """
    if week_start:
        target_week = date.fromisoformat(week_start)
    else:
        target_week = db.exec(
            select(WeeklyLocationPerformance.week_start)
            .order_by(WeeklyLocationPerformance.week_start.desc())
        ).first()
        if target_week is None:
            return {"week_start": None, "locations": []}

    rows = db.exec(
        select(WeeklyLocationPerformance).where(
            WeeklyLocationPerformance.week_start == target_week
        )
    ).all()

    return {
        "week_start": target_week.isoformat(),
        "locations": [
            {
                "location_id": row.location_id,
                "country": row.country,
                "total_purchase_cost": row.total_purchase_cost,
                "total_waste_cost": row.total_waste_cost,
                "waste_ratio": row.waste_ratio,
                "stockout_events_count": row.stockout_events_count,
                "price_alert_events_count": row.price_alert_events_count,
                "currency": row.currency,
            }
            for row in rows
        ],
    }


@router.get("/pipeline-runs/latest")
def get_latest_pipeline_run(db: Session = Depends(get_db)):
    """Status query -- metadata of the last pipeline run, from
    reporting.pipeline_runs. Lets anyone check whether this week's
    report actually computed without needing direct database access --
    see PIPELINE_DESIGN.md's Observability section for why this table
    exists at all.
    """
    run = db.exec(select(PipelineRun).order_by(PipelineRun.started_at.desc())).first()
    if run is None:
        return {"run": None}
    return {
        "run_id": run.run_id,
        "week_start": run.week_start.isoformat(),
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "records_processed": run.records_processed,
        "locations_written": run.locations_written,
        "error_message": run.error_message,
    }


@router.post("/pipeline-runs")
def trigger_pipeline_run(week_start: Optional[str] = None):
    """Manual trigger -- runs weekly_location_performance_flow
    synchronously and returns its result. Imports and calls the flow
    directly rather than duplicating any of its logic here, per the
    ticket's "no ETL logic belongs in services/" rule.

    Runs in-request (blocking) rather than handed off to a background
    worker -- reasonable at this scale (14 rows, a handful of seconds),
    and keeps this milestone's scope to what PIPELINE_DESIGN.md actually
    designed. A queue would be the first thing to add if that stops
    being true.
    """
    target_week = date.fromisoformat(week_start) if week_start else None
    return weekly_location_performance_flow(week_start=target_week, triggered_by="manual")
