"""
celery_app.py -- Celery application for Brasaland's async task queue
(DEV-55).

Redis is used as both the message broker and the result backend -- one
REDIS_URL, read from the environment the same way database.py reads
DATABASE_URL. Workers run as a separate process, never inside the
FastAPI process itself:
    uv run celery -A celery_app worker --loglevel=info
(or, in Docker, the `worker` service in docker-compose.yml runs that
same command in its own container).

Only one task lives in this codebase so far -- see tasks.py, which
wraps the operation that used to run in-request inside
routes/reporting.py's POST /reporting/pipeline-runs.
"""

import os
import sys
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# data/pipelines/ isn't part of this package -- same hand-rolled
# sys.path treatment routes/reporting.py already uses to import the
# flow tasks.py calls (see that file's own comment: REPO_ROOT is
# `parents[N]` levels up based on how deep *this* file sits under the
# repo root). celery_app.py lives at services/api/celery_app.py, two
# levels down from the root.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))

celery_app = Celery(
    "brasaland",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery_app.conf.update(
    # Without this, Celery only ever reports "pending" or a final
    # state -- GET /tasks/{task_id} needs "started" to be a real,
    # reachable state (per DEV-55's acceptance criteria), not just
    # something that exists in theory.
    task_track_started=True,
    # Rule #3 from the ticket: every task needs a maximum execution
    # time, or a worker that never finishes blocks the whole pool.
    # Soft limit raises inside the task first (catchable, for cleanup);
    # hard limit kills it outright 30s later if that didn't work.
    task_time_limit=300,
    task_soft_time_limit=270,
    # Task results (state + return value) expire after an hour --
    # long enough to poll during development without Redis holding
    # results forever.
    result_expires=3600,
    # If the worker starts before Redis is ready (e.g. `docker compose
    # up` racing container startup), keep retrying the connection
    # instead of crashing immediately.
    broker_connection_retry_on_startup=True,
)
