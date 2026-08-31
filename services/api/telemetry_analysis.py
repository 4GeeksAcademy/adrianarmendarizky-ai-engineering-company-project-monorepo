"""
telemetry_analysis.py -- the operational analysis pipeline for telemetry_events.

Lives inside services/api (not a separate services/telemetry/ service,
as the assignment brief's example path suggests) since nothing here
needs to be shared outside the API. The only two directories this
codebase actually shares across services (scripts/, packages/shared/)
are wired into services/Dockerfile explicitly, with hand-rolled
sys.path manipulation in the files that use them -- adding a third
shared location here for a file that's only ever called from
routes/telemetry.py would mean touching that Dockerfile,
docker-compose.yml's volume mounts, and replicating that same
sys.path pattern, for no benefit over just keeping it where the rest
of this feature's own files already live.

Every function below follows the same fixed order, per the brief:
    load (SQL, filtered) -> refine (Pandas) -> convert types -> group -> aggregate
Each is pure and side-effect free -- same (db, start_date, end_date)
in, same list of dicts out, every time. No loops anywhere -- only
Pandas operations (groupby/agg/count/mean/sum).

These are technical/operational metrics only: volume, errors, latency,
which event types dominate. No conversion rates, revenue, or other
business metrics -- that analysis belongs to a later Data Pipelines
milestone, not here.
"""

from datetime import datetime

import pandas as pd
from sqlmodel import Session, select

from telemetry_models import TelemetryEventRecord


def _load_events(
    db: Session,
    start_date: datetime,
    end_date: datetime,
    event_types: list[str] | None = None,
) -> pd.DataFrame:
    """The SQL half of the formula, shared by every metric below.

    Filters by timestamp range -- and, when given, a specific set of
    event_types -- at the database layer. Never loads the whole table
    and filters in Pandas afterward; that's the difference between a
    query that scales and one that doesn't. Returns an empty,
    correctly-shaped DataFrame (not None) when nothing matches, so
    every metric function can groupby/agg it without a special case.
    """
    query = select(TelemetryEventRecord).where(
        TelemetryEventRecord.timestamp >= start_date,
        TelemetryEventRecord.timestamp < end_date,
    )
    if event_types:
        query = query.where(TelemetryEventRecord.event_type.in_(event_types))

    rows = db.exec(query).all()
    if not rows:
        return pd.DataFrame(columns=["event_id", "timestamp", "event_type", "tags"])

    return pd.DataFrame(
        [
            {
                "event_id": r.event_id,
                "timestamp": r.timestamp,
                "event_type": r.event_type,
                "tags": r.tags,
            }
            for r in rows
        ]
    )


def _to_native(records: list[dict]) -> list[dict]:
    """Pandas/NumPy scalar types (int64, float64, bool_) aren't JSON-
    serializable as-is -- FastAPI's default encoder chokes on them.
    Converts every value in every dict back to a plain Python type
    before this leaves the analysis layer, so routes/telemetry.py never
    has to think about it.
    """
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in records]


def events_per_day(db: Session, start_date: datetime, end_date: datetime) -> list[dict]:
    """Total event volume, grouped by day.

    Answers: is the system busier or quieter than usual, day to day?
    """
    df = _load_events(db, start_date, end_date)
    if df.empty:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date.astype(str)

    result = df.groupby("date").agg(count=("event_id", "count")).reset_index()
    return _to_native(result.to_dict(orient="records"))


def events_by_type_per_day(db: Session, start_date: datetime, end_date: datetime) -> list[dict]:
    """Event volume grouped by day AND event_type.

    Answers: which event types dominate, and does that mix change day
    to day (e.g. a spike in one particular type on one particular day)?
    """
    df = _load_events(db, start_date, end_date)
    if df.empty:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date.astype(str)

    result = (
        df.groupby(["date", "event_type"]).agg(count=("event_id", "count")).reset_index()
    )
    return _to_native(result.to_dict(orient="records"))


def api_error_rate_per_day(db: Session, start_date: datetime, end_date: datetime) -> list[dict]:
    """Share of api_latency_recorded calls that came back 4xx/5xx, by day.

    Answers: is the API getting less reliable, and on which day did
    that start?
    """
    df = _load_events(db, start_date, end_date, event_types=["api_latency_recorded"])
    if df.empty:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["status_code"] = df["tags"].apply(lambda t: t.get("status_code"))
    df = df.dropna(subset=["status_code"])
    df["is_error"] = df["status_code"] >= 400

    result = (
        df.groupby("date")
        .agg(total=("event_id", "count"), errors=("is_error", "sum"))
        .reset_index()
    )
    result["error_rate"] = (result["errors"] / result["total"]).round(4)
    return _to_native(result[["date", "total", "errors", "error_rate"]].to_dict(orient="records"))


def api_latency_avg_ms_per_day(db: Session, start_date: datetime, end_date: datetime) -> list[dict]:
    """Average API call latency (ms), by day.

    Answers: is the system getting slower, and since when?
    """
    df = _load_events(db, start_date, end_date, event_types=["api_latency_recorded"])
    if df.empty:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["duration_ms"] = df["tags"].apply(lambda t: t.get("duration_ms"))
    df = df.dropna(subset=["duration_ms"])

    result = df.groupby("date").agg(avg_duration_ms=("duration_ms", "mean")).reset_index()
    result["avg_duration_ms"] = result["avg_duration_ms"].round(1)
    return _to_native(result.to_dict(orient="records"))


def auth_failure_rate_per_day(db: Session, start_date: datetime, end_date: datetime) -> list[dict]:
    """Additional Activity: daily login failure rate.

    user_login_failed / (user_login_failed + user_login_succeeded), by
    day. Answers: are logins becoming less reliable -- broken UX,
    expired sessions piling up, or a brute-force attempt?
    """
    df = _load_events(
        db, start_date, end_date, event_types=["user_login_failed", "user_login_succeeded"]
    )
    if df.empty:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date.astype(str)
    df["is_failure"] = df["event_type"] == "user_login_failed"

    result = (
        df.groupby("date")
        .agg(total_attempts=("event_id", "count"), failures=("is_failure", "sum"))
        .reset_index()
    )
    result["auth_failure_rate"] = (result["failures"] / result["total_attempts"]).round(4)
    return _to_native(
        result[["date", "total_attempts", "failures", "auth_failure_rate"]].to_dict(
            orient="records"
        )
    )
