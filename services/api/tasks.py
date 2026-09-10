"""
tasks.py -- Celery task definitions (DEV-55).

Kept separate from celery_app.py so the app object itself doesn't need
every task's imports (this task pulls in pandas/prefect indirectly via
pipeline.py) -- celery_app.py just points here via `include=["tasks"]`.

Only one task so far: run_weekly_performance_report, converting
POST /reporting/pipeline-runs (routes/reporting.py) from a blocking,
in-request call into a background job.
"""

import logging
import time
from datetime import date
from typing import Optional

from sqlmodel import Session

from celery_app import celery_app
from database import engine
from dlq_models import TaskFailure

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.run_weekly_performance_report", max_retries=3)
def run_weekly_performance_report(self, week_start: Optional[str] = None, triggered_by: str = "async"):
    """Runs weekly_location_performance_flow in the background.

    Message payload is just week_start (an ISO date string, or None
    for "most recent Monday") and triggered_by -- small references,
    never the report data itself (rule #1 from the ticket: keep
    messages lightweight, never put a full data batch in the message).

    Retries up to max_retries=3 times with exponential backoff (10s,
    20s, 40s -- never immediately, per rule #2). Once retries are
    exhausted, the failure is written to task_failures (see
    dlq_models.py) with the task_id, attempt number, and error message,
    then re-raised so Celery/Flower still show the task as FAILURE.
    """
    attempt = self.request.retries + 1
    started = time.monotonic()
    parsed_week_start = date.fromisoformat(week_start) if week_start else None

    try:
        # Imported inside the try, not at module level: pipeline.py only
        # becomes importable once celery_app.py has added
        # data/pipelines/ to sys.path (done once, when celery_app loads
        # -- always before this module, via `include=["tasks"]"). Doing
        # the import in here too means a failure at import time still
        # goes through the same retry/backoff/DLQ path below, instead
        # of crashing before the try block ever runs.
        from pipeline import weekly_location_performance_flow




        result = weekly_location_performance_flow(
            week_start=parsed_week_start, triggered_by=triggered_by
        )
        duration = time.monotonic() - started
        logger.info(
            "task_id=%s attempt=%s status=success duration=%.2fs",
            self.request.id, attempt, duration,
        )
        return result
    except Exception as exc:
        duration = time.monotonic() - started
        logger.error(
            "task_id=%s attempt=%s status=failure duration=%.2fs error=%s",
            self.request.id, attempt, duration, exc,
        )
        # 10s, 20s, 40s between attempts.
        if attempt > self.max_retries:
            _record_dead_letter(self.request.id, attempt, str(exc))
            raise
        countdown = 10 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


def _record_dead_letter(task_id: str, attempt: int, error_message: str) -> None:
    """Writes one task_failures row. Mirrors database.get_db()'s own
    "raise loudly if DATABASE_URL is unset" stance is skipped here on
    purpose -- a missing DB shouldn't hide the fact that the task also
    failed, so this only logs and returns instead of raising a second
    error on top of the one already being handled.
    """
    if engine is None:
        logger.error(
            "DATABASE_URL not set -- could not record DLQ entry for task_id=%s", task_id
        )
        return
    with Session(engine) as session:
        session.add(TaskFailure(task_id=task_id, attempt=attempt, error_message=error_message))
        session.commit()
