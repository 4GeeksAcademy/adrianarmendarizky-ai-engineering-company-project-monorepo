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

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from database import get_db
from reporting_models import PipelineRun, WeeklyLocationPerformance
from tasks import run_weekly_performance_report

# DEV-55: pipeline.py (data/pipelines/) is no longer imported here --
# POST /pipeline-runs below now enqueues tasks.run_weekly_performance_report
# instead of calling the flow directly, and that task is the one that
# needs data/pipelines/ on sys.path (see celery_app.py, which sets that
# up once for every task, not per-route).
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


@router.post("/pipeline-runs", status_code=status.HTTP_202_ACCEPTED)
def trigger_pipeline_run(week_start: Optional[str] = None):
    """Manual trigger (DEV-55) -- enqueues weekly_location_performance_flow
    as a background Celery task and returns immediately with a task_id,
    instead of running the flow in-request.

    Picked as DEV-55's conversion candidate because it was already the
    one blocking, synchronous operation in this API -- this endpoint's
    own previous docstring said a queue would be "the first thing to
    add" once running in-request stopped being fast enough. See
    GET /tasks/{task_id} (routes/tasks.py) to check status/result, and
    tasks.py for the task itself (retries, backoff, and the DLQ).

    week_start is passed through as a plain ISO string (or left out) --
    not the flow's own `date` object -- since the message that goes
    into Redis has to be JSON-serializable and small (see tasks.py's
    docstring on keeping messages lightweight).
    """
    task = run_weekly_performance_report.delay(week_start=week_start, triggered_by="async")
    return {"task_id": task.id}
