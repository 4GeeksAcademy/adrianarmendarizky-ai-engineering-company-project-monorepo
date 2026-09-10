"""
dlq_models.py -- SQLModel ORM class for the async task queue's Dead
Letter Queue (DEV-55).

One row per task that failed on every attempt (initial run plus all
retries). Lives in the default `public` schema, not `reporting` --
same reasoning as job_runs_models.py: this table isn't specific to one
pipeline, so a future task type (not just
tasks.run_weekly_performance_report) can write here too without the
table needing to move.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class TaskFailure(SQLModel, table=True):
    __tablename__ = "task_failures"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_id: str
    # Which attempt this was (1 = the initial run, 2+ = retries) --
    # the acceptance criteria asks for this explicitly, alongside
    # task_id and the error message.
    attempt: int
    error_message: str
    failed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    )
