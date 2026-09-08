"""
scripts/nightly_export.py -- nightly orchestration: export the previous
day's telemetry_events to a CSV backup, then trigger the Milestone 6
pipeline (data/pipelines/pipeline.py) as a subprocess.

This script is the only thing that writes to job_runs
(services/api/job_runs_models.py). It's its own independent process --
never imported into or run from the FastAPI app. job_runs tracks THIS
script's own executions; reporting.pipeline_runs (written by
pipeline.py itself, during its own run) is a separate log for a
separate layer -- see job_runs_models.py's docstring for why the two
stay separate.

CSV is a backup, not the pipeline's input. If the CSV already exists
for target_date, the export step is skipped, but the pipeline is
still triggered -- a previous run could have written the CSV and then
died before finishing (see the "processing" lock below).

Usage:
    cd services/api && uv run python ../../scripts/nightly_export.py
    TARGET_DATE=2025-01-15 uv run python ../../scripts/nightly_export.py
"""

import csv
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# services/api isn't scripts/'s own package, so it needs the same
# hand-rolled sys.path treatment already used elsewhere in this repo
# to reach a sibling directory (see routes/reporting.py's REPO_ROOT /
# "data" / "pipelines" version of this same pattern).
REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICES_API_DIR = REPO_ROOT / "services" / "api"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from sqlmodel import Session, select  # noqa: E402

from database import engine  # noqa: E402
from job_runs_models import JobRun  # noqa: E402
from telemetry_models import TelemetryEventRecord  # noqa: E402

JOB_NAME = "nightly_export"
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
PIPELINE_ENTRY = REPO_ROOT / "data" / "pipelines" / "pipeline.py"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(JOB_NAME)


def _log(level: int, status: str, target_date: date, message: str) -> None:
    """Every line carries job_name, status, and target_date literally,
    so a log line answers "which job, which day, what happened" on
    its own."""
    logger.log(
        level,
        "job_name=%s status=%s target_date=%s message=%s",
        JOB_NAME, status, target_date.isoformat(), message,
    )


def resolve_target_date() -> date:
    """TARGET_DATE env overrides; otherwise yesterday in UTC."""
    override = os.getenv("TARGET_DATE")
    if override:
        return date.fromisoformat(override)
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def find_processing_run(db: Session):
    """The distributed lock: any job_runs row for this job_name still
    'processing' means another run is in flight, for any target_date."""
    return db.exec(
        select(JobRun).where(JobRun.job_name == JOB_NAME, JobRun.status == "processing")
    ).first()


def find_completed_run(db: Session, target_date: date):
    """Per-day idempotency: has this exact day already succeeded?"""
    return db.exec(
        select(JobRun).where(
            JobRun.job_name == JOB_NAME,
            JobRun.target_date == target_date,
            JobRun.status == "completed",
        )
    ).first()


def export_csv(db: Session, target_date: date) -> Path:
    csv_path = DATA_RAW_DIR / f"telemetry_{target_date.isoformat()}.csv"
    if csv_path.exists():
        _log(logging.INFO, "processing", target_date, f"CSV already exists, skipping export: {csv_path}")
        return csv_path

    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    rows = db.exec(
        select(TelemetryEventRecord).where(
            TelemetryEventRecord.timestamp >= day_start,
            TelemetryEventRecord.timestamp < day_end,
        )
    ).all()

    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["event_id", "timestamp", "session_id", "user_id", "event_type", "schema_version", "request_id", "tags"]
        )
        for row in rows:
            writer.writerow(
                [row.event_id, row.timestamp.isoformat(), row.session_id, row.user_id,
                 row.event_type, row.schema_version, row.request_id, row.tags]
            )

    _log(logging.INFO, "processing", target_date, f"exported {len(rows)} rows to {csv_path}")
    return csv_path


def trigger_pipeline(target_date: date) -> None:
    """Subprocess, not an import -- runs pipeline.py the same way it
    documents its own invocation: `cd services/api && uv run python
    ../../data/pipelines/pipeline.py`. `uv run` matters here --
    pipeline.py's imports (prefect, sqlmodel) live inside services/api's
    own uv-managed .venv, not necessarily whatever Python this script
    is running under. --triggered-by schedule is the flag pipeline.py's
    own argparse already supports for exactly this case.
    """
    result = subprocess.run(
        ["uv", "run", "python", str(PIPELINE_ENTRY), "--triggered-by", "schedule"],
        cwd=str(SERVICES_API_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pipeline subprocess exited {result.returncode}: {result.stderr.strip()[-2000:]}"
        )
    _log(logging.INFO, "processing", target_date, f"pipeline subprocess finished: {result.stdout.strip()[-500:]}")


def main() -> None:
    target_date = resolve_target_date()
    _log(logging.INFO, "pending", target_date, "starting nightly export")

    with Session(engine) as db:
        if find_processing_run(db) is not None:
            _log(logging.INFO, "processing", target_date, "skipped: another run is already processing")
            return

        if find_completed_run(db, target_date) is not None:
            _log(logging.INFO, "completed", target_date, "skipped: already completed for this target_date")
            return

        job_run = JobRun(job_name=JOB_NAME, target_date=target_date, status="processing")
        db.add(job_run)
        db.commit()
        db.refresh(job_run)

    try:
        with Session(engine) as db:
            export_csv(db, target_date)

        trigger_pipeline(target_date)

        with Session(engine) as db:
            run = db.get(JobRun, job_run.id)
            run.status = "completed"
            db.add(run)
            db.commit()
        _log(logging.INFO, "completed", target_date, "finished successfully")

    except Exception as exc:
        with Session(engine) as db:
            run = db.get(JobRun, job_run.id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            db.add(run)
            db.commit()
        _log(logging.ERROR, "failed", target_date, str(exc))
        raise


if __name__ == "__main__":
    main()