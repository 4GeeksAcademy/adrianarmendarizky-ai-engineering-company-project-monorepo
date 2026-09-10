"""
routes/tasks.py -- generic Celery task-status endpoint (DEV-55).

Not tied to any one task type -- GET /tasks/{task_id} works for
whatever task_id a producer endpoint handed back (today, only
POST /reporting/pipeline-runs does), the same way Celery's own
AsyncResult does internally. A second async endpoint later wouldn't
need a second version of this route.
"""

from celery.result import AsyncResult
from fastapi import APIRouter

from celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Celery's own states, lowercased to match this API's existing
# status-column convention (see job_runs_models.py / reporting_models.py):
# PENDING/STARTED/SUCCESS/FAILURE on the wire become pending/started/
# success/failure. RETRY reads as "started" to a client -- it's still
# in progress, just between attempts.
_STATUS_MAP = {
    "PENDING": "pending",
    "STARTED": "started",
    "RETRY": "started",
    "SUCCESS": "success",
    "FAILURE": "failure",
}


@router.get("/{task_id}")
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    status = _STATUS_MAP.get(task_result.state, task_result.state.lower())

    if status == "success":
        result = task_result.result
    elif status == "failure":
        # After every retry is exhausted, .result holds the exception
        # object Celery caught -- stringify it so the response is valid
        # JSON instead of erroring on serialization.
        result = {"error": str(task_result.result)}
    else:
        result = None

    return {"task_id": task_id, "status": status, "result": result}
