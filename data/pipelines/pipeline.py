"""
data/pipelines/pipeline.py -- Weekly Location Cost & Waste Report pipeline.

Reads from telemetry_events (read-only), writes to
reporting.weekly_location_performance and reporting.pipeline_runs.
services/telemetry/analysis.py and GET /telemetry/report are untouched --
see PIPELINE_DESIGN.md for the full design this implements.

Run as a script:
    cd services/api && uv run python ../../data/pipelines/pipeline.py
    cd services/api && uv run python ../../data/pipelines/pipeline.py --week-start 2026-08-24

Requires DATABASE_URL in services/api/.env -- same Supabase connection
the rest of the app uses. Requires prefect>=3 (services/api/pyproject.toml).

services/api holds the SQLModel table classes and the DB engine this
pipeline reads/writes through, so it's added to sys.path below -- the
same hand-rolled sys.path pattern already used elsewhere in this repo to
reach a sibling directory that isn't its own installable package (see
scripts/analyze.py and services/api/app/incidents/controller.py).
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from prefect import flow, task  # noqa: E402
from sqlalchemy import func  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from database import engine  # noqa: E402
from reporting_models import PipelineRun, WeeklyLocationPerformance  # noqa: E402
from telemetry_models import TelemetryEventRecord  # noqa: E402

# The five event types this report is built from, per CONTEXT-brasaland.md
# section 3. outbound_order_created is extracted alongside the others for
# volume context but has no KPI column of its own in v1 -- "resist the
# urge to widen scope."
RELEVANT_EVENT_TYPES = [
    "inbound_order_created",
    "outbound_order_created",
    "stock_waste_registered",
    "stock_threshold_triggered",
    "ingredient_price_variance_detected",
]

# Placeholder location_id -> country mapping. Only 1 and 8 are populated,
# because those are the only location_ids that appear anywhere in
# seed_inventory.py's data today: location 1 buys CO-menu ingredients
# (Ingredient.country="CO"), location 8 buys US-menu ingredients
# (Ingredient.country="US"). This is NOT a claim that those are the only
# real locations, or that the pattern holds for the other 12 -- it's
# exactly the honest-gap approach PIPELINE_DESIGN.md's "Schema
# prerequisite #2" describes: don't guess the rest of a 14-location list
# from six rows of seed data. Any location_id seen in telemetry_events
# that isn't in this dict gets flagged by write_validation_snapshot below
# and skipped, not silently written with a guessed currency. Replace with
# the real 14-location list from Operations before this goes to production.
LOCATION_REGISTRY: dict[int, str] = {
    1: "CO",
    8: "US",
}
CURRENCY_BY_COUNTRY = {"CO": "COP", "US": "USD"}


def _most_recent_monday(today: Optional[date] = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=today.weekday())  # Monday == 0


def _transform_cache_key(context, parameters) -> str:
    """Same week + same set of event_ids should reuse the already-computed
    result instead of re-aggregating -- this is the 'expensive
    transformation task' the resilience ticket asks for caching on. Keyed
    on event_ids (not just week_start) so a genuinely new event landing
    for the same week still busts the cache, matching the idempotency
    rule that a recompute must reflect whatever telemetry_events actually
    holds right now.
    """
    week_start = parameters["week_start"]
    event_ids = tuple(sorted(e.event_id for e in parameters["events"]))
    return f"transform:{week_start}:{hash(event_ids)}"


@task(
    name="extract-weekly-events",
    # Touches Supabase -- the resilience ticket requires retries on any
    # task that touches an external service. Increasing delays (10s, 30s,
    # 60s) rather than immediate retries, since a dropped connection is
    # the likeliest transient failure here (PIPELINE_DESIGN.md's
    # Recoverability §1) and usually clears within a minute, not instantly.
    retries=3,
    retry_delay_seconds=[10, 30, 60],
)
def extract_weekly_events(week_start: date) -> list[TelemetryEventRecord]:
    """Reads telemetry_events for the target week -- read-only, per
    CONTEXT-brasaland.md section 7. Never touches services/telemetry/
    or GET /telemetry/report.
    """
    week_start_dt = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    week_end_dt = week_start_dt + timedelta(days=7)

    with Session(engine) as db:
        events = db.exec(
            select(TelemetryEventRecord).where(
                TelemetryEventRecord.event_type.in_(RELEVANT_EVENT_TYPES),
                TelemetryEventRecord.timestamp >= week_start_dt,
                TelemetryEventRecord.timestamp < week_end_dt,
            )
        ).all()

    # Defensive de-dup on event_id -- event_id is already telemetry_events'
    # primary key, so a true duplicate can't exist there, but this
    # pipeline reads read-only and shouldn't have to trust that guarantee
    # blindly. See PIPELINE_DESIGN.md's Idempotency §1.
    deduped: dict[str, TelemetryEventRecord] = {}
    for event in events:
        deduped.setdefault(event.event_id, event)
    return list(deduped.values())


@task(
    name="transform-location-metrics",
    cache_key_fn=_transform_cache_key,
    cache_expiration=timedelta(hours=1),
)
def transform_location_metrics(
    events: list[TelemetryEventRecord], week_start: date
) -> tuple[list[dict], list[int]]:
    """Groups events by location_id and computes the five KPIs from
    CONTEXT-brasaland.md section 2. Pure function -- no database access --
    so it's testable on its own and safe to cache.

    Returns (rows, unmatched_location_ids): rows are ready to upsert;
    unmatched_location_ids are location_ids seen in this week's events
    with no entry in LOCATION_REGISTRY, which get skipped here (see the
    registry's own docstring above) rather than written with a guessed
    currency.
    """
    by_location: dict[int, list[TelemetryEventRecord]] = defaultdict(list)
    for event in events:
        location_id = event.tags.get("location_id")
        if location_id is not None:
            by_location[location_id].append(event)

    rows: list[dict] = []
    unmatched_location_ids: list[int] = []

    for location_id, location_events in by_location.items():
        country = LOCATION_REGISTRY.get(location_id)
        if country is None:
            unmatched_location_ids.append(location_id)
            continue

        currency = CURRENCY_BY_COUNTRY[country]
        total_purchase_cost = 0.0
        total_waste_cost = 0.0
        stockout_events_count = 0
        price_alert_events_count = 0

        for event in location_events:
            tags = event.tags
            if event.event_type == "inbound_order_created":
                unit_cost = tags.get("unit_cost")
                if unit_cost is not None:
                    total_purchase_cost += unit_cost * tags.get("quantity", 0)
            elif event.event_type == "stock_waste_registered":
                unit_cost = tags.get("unit_cost")
                if unit_cost is not None:
                    total_waste_cost += unit_cost * tags.get("quantity", 0)
            elif event.event_type == "stock_threshold_triggered":
                stockout_events_count += 1
            elif event.event_type == "ingredient_price_variance_detected":
                price_alert_events_count += 1
            # outbound_order_created: volume context only, no KPI column
            # for it in v1 -- see RELEVANT_EVENT_TYPES's comment above.

        waste_ratio = (
            total_waste_cost / total_purchase_cost if total_purchase_cost else 0.0
        )

        rows.append(
            {
                # Destination column is `text not null`
                # (CONTEXT-brasaland.md section 5); telemetry's own
                # location_id is an integer -- cast at the boundary.
                "location_id": str(location_id),
                "country": country,
                "week_start": week_start,
                "total_purchase_cost": round(total_purchase_cost, 2),
                "total_waste_cost": round(total_waste_cost, 2),
                "waste_ratio": round(waste_ratio, 4),
                "stockout_events_count": stockout_events_count,
                "price_alert_events_count": price_alert_events_count,
                "currency": currency,
            }
        )

    return rows, unmatched_location_ids


@task(name="write-validation-snapshot")
def write_validation_snapshot(unmatched_location_ids: list[int], week_start: date) -> None:
    """Non-critical: writes any location_ids seen this week but missing
    from LOCATION_REGISTRY to data/eval/, so a registry gap is visible in
    version control instead of silently-skipped rows. Called with
    return_state=True in the flow below -- a disk/permissions problem
    writing this file should never stop the actual report from loading.
    """
    if not unmatched_location_ids:
        return
    eval_dir = REPO_ROOT / "data" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    out_path = eval_dir / f"unmatched_locations_{week_start.isoformat()}.json"
    out_path.write_text(
        json.dumps(
            {
                "week_start": week_start.isoformat(),
                "unmatched_location_ids": sorted(unmatched_location_ids),
                "note": (
                    "These location_ids appeared in telemetry_events for this week "
                    "but have no country in LOCATION_REGISTRY (data/pipelines/pipeline.py). "
                    "Their rows were skipped, not written with a guessed currency."
                ),
            },
            indent=2,
        )
    )


@task(
    name="load-weekly-performance",
    # Also touches Supabase -- same reasoning and same backoff as
    # extract-weekly-events above.
    retries=3,
    retry_delay_seconds=[10, 30, 60],
)
def load_weekly_performance(rows: list[dict]) -> int:
    """Upserts each row into reporting.weekly_location_performance, keyed
    on (location_id, week_start) -- the table's own unique constraint
    (CONTEXT-brasaland.md section 5). Postgres' ON CONFLICT ... DO UPDATE
    is what makes a re-run of the same week idempotent: it always
    overwrites that week's rows with freshly recomputed numbers, never
    duplicates them. See PIPELINE_DESIGN.md's Idempotency strategy and
    Update strategy sections.
    """
    if not rows:
        return 0

    stmt = pg_insert(WeeklyLocationPerformance).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["location_id", "week_start"],
        set_={
            "total_purchase_cost": stmt.excluded.total_purchase_cost,
            "total_waste_cost": stmt.excluded.total_waste_cost,
            "waste_ratio": stmt.excluded.waste_ratio,
            "stockout_events_count": stmt.excluded.stockout_events_count,
            "price_alert_events_count": stmt.excluded.price_alert_events_count,
            "currency": stmt.excluded.currency,
            "computed_at": func.now(),
        },
    )
    with Session(engine) as db:
        db.execute(stmt)
        db.commit()
    return len(rows)


def _write_run_start(run_id: str, week_start: date, triggered_by: str) -> None:
    with Session(engine) as db:
        db.add(
            PipelineRun(
                run_id=run_id,
                week_start=week_start,
                triggered_by=triggered_by,
                started_at=datetime.now(timezone.utc),
                status="Running",
            )
        )
        db.commit()


def _write_run_complete(run_id: str, records_processed: int, locations_written: int) -> None:
    with Session(engine) as db:
        run = db.get(PipelineRun, run_id)
        if run is None:
            return
        run.completed_at = datetime.now(timezone.utc)
        run.status = "Completed"
        run.records_processed = records_processed
        run.locations_written = locations_written
        db.add(run)
        db.commit()


def _write_run_failed(run_id: str, error_message: str) -> None:
    with Session(engine) as db:
        run = db.get(PipelineRun, run_id)
        if run is None:
            return
        run.completed_at = datetime.now(timezone.utc)
        run.status = "Failed"
        run.error_message = error_message[:2000]
        db.add(run)
        db.commit()


@flow(name="weekly-location-performance")
def weekly_location_performance_flow(
    week_start: Optional[date] = None, triggered_by: str = "manual"
) -> dict:
    """Main flow -- extraction, transformation, and load for one week.

    Wraps the whole body in try/except so ANY unhandled failure --
    including one that survives a task's own retries -- still gets
    recorded as reporting.pipeline_runs.status="Failed" with an
    error_message, not just silently dropped. This is on top of, not
    instead of, the per-task retries above.
    """
    week_start = week_start or _most_recent_monday()
    run_id = str(uuid4())
    _write_run_start(run_id, week_start, triggered_by)

    try:
        events = extract_weekly_events(week_start)
        rows, unmatched_location_ids = transform_location_metrics(events, week_start)

        # Optional/non-critical step, invoked with return_state=True so a
        # failure here is logged and the flow keeps going rather than
        # crashing the whole run -- see the resilience ticket's "tolerate
        # partial failures" requirement.
        snapshot_state = write_validation_snapshot(
            unmatched_location_ids, week_start, return_state=True
        )
        if snapshot_state.is_failed():
            print(f"[pipeline] validation snapshot failed (non-critical): {snapshot_state}")

        locations_written = load_weekly_performance(rows)
        _write_run_complete(
            run_id, records_processed=len(events), locations_written=locations_written
        )
        return {
            "run_id": run_id,
            "week_start": week_start.isoformat(),
            "locations_written": locations_written,
        }
    except Exception as exc:
        _write_run_failed(run_id, error_message=str(exc))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Weekly Location Cost & Waste Report pipeline."
    )
    parser.add_argument(
        "--week-start",
        type=str,
        default=None,
        help="ISO date (a Monday) of the week to compute. Defaults to the most recent Monday.",
    )
    parser.add_argument(
        "--triggered-by",
        type=str,
        default="manual",
        choices=["manual", "schedule"],
    )
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start) if args.week_start else None
    result = weekly_location_performance_flow(week_start=week_start, triggered_by=args.triggered_by)
    print(result)


if __name__ == "__main__":
    main()
