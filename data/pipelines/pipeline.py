"""
data/pipelines/pipeline.py -- Weekly Location Cost & Waste Report pipeline.

Reads from telemetry_events (read-only), writes to
reporting.weekly_location_performance and reporting.pipeline_runs.
services/telemetry/analysis.py and GET /telemetry/report are untouched --
see PIPELINE_DESIGN.md for the full design this implements.

Part 3 refactor: the main flow no longer contains any ETL logic itself --
it coordinates four subflows (extraction, transformation, load, plus the
optional flag-unmatched-locations step), each independently runnable with
explicit inputs/outputs. The transformation stage, which used to be one
task computing all five KPIs together, is now five small tasks -- one per
KPI in CONTEXT-brasaland.md's "KPIs to Measure" section -- plus one
assembly task that joins them into destination-table rows. See
tests/pipelines/test_pipeline.py for unit tests on each KPI task.

Run as a script (entrypoint unchanged from Part 2):
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
# that isn't in this dict gets flagged by flag_unmatched_locations_flow
# below and skipped, not silently written with a guessed currency.
# Replace with the real 14-location list from Operations before this goes
# to production.
LOCATION_REGISTRY: dict[int, str] = {
    1: "CO",
    8: "US",
}
CURRENCY_BY_COUNTRY = {"CO": "COP", "US": "USD"}


def _most_recent_monday(today: Optional[date] = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=today.weekday())  # Monday == 0


# ---------------------------------------------------------------------
# Extraction -- one task (Supabase-facing, retrying), one subflow.
# ---------------------------------------------------------------------


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


@flow(name="extract-cost-and-waste-events")
def extract_cost_and_waste_events_flow(week_start: date) -> list[TelemetryEventRecord]:
    """Extraction subflow -- Part 3's required first stage. Thin wrapper
    around the retrying task above, kept as its own flow so extraction
    can be run, monitored, and reused independently of transform or load.
    Explicit input (week_start), explicit output (the event list) -- no
    shared state with the other subflows beyond what's passed between them.
    """
    return extract_weekly_events(week_start)


# ---------------------------------------------------------------------
# Transformation -- five tasks, one per KPI in CONTEXT-brasaland.md's
# "KPIs to Measure" section, plus one assembly task. All five KPI tasks
# are pure functions (no database, no external calls) -- see
# tests/pipelines/test_pipeline.py for unit tests on each.
# ---------------------------------------------------------------------


def _cost_cache_key(context, parameters) -> str:
    """Same event set should reuse the already-computed cost total
    instead of re-scanning -- carries Part 2's caching requirement
    forward onto whichever task actually does the expensive scan, now
    that transform is split into several smaller tasks. Keyed on
    event_ids (not a fixed window) so a genuinely new event still busts
    the cache -- same reasoning as Part 2's original cache key. Includes
    the task's own name so compute-purchase-cost-per-location and
    compute-waste-cost-per-location (which share this same cache_key_fn)
    never collide on the same key for the same event set.
    """
    events = parameters["events"]
    event_ids = tuple(sorted(e.event_id for e in events))
    return f"{context.task.name}:{hash(event_ids)}"


@task(
    name="compute-purchase-cost-per-location",
    cache_key_fn=_cost_cache_key,
    cache_expiration=timedelta(hours=1),
)
def compute_purchase_cost_per_location(
    events: list[TelemetryEventRecord],
) -> dict[int, float]:
    """Purchase Cost per Location (CONTEXT-brasaland.md 'KPIs to
    Measure'): sum of inbound_order_created costs for the week, per
    location. quantity * unit_cost per event. An event missing
    location_id or unit_cost is skipped entirely (can't attribute or
    price it); a missing quantity defaults to 0 rather than skipping the
    event, matching how every other optional telemetry field in this
    pipeline is treated -- see PIPELINE_DESIGN.md's Schema prerequisite #1.
    """
    totals: dict[int, float] = defaultdict(float)
    for event in events:
        if event.event_type != "inbound_order_created":
            continue
        tags = event.tags or {}
        location_id = tags.get("location_id")
        if location_id is None:
            continue
        unit_cost = tags.get("unit_cost")
        if unit_cost is None:
            continue
        totals[location_id] += unit_cost * tags.get("quantity", 0)
    return dict(totals)


@task(
    name="compute-waste-cost-per-location",
    cache_key_fn=_cost_cache_key,
    cache_expiration=timedelta(hours=1),
)
def compute_waste_cost_per_location(
    events: list[TelemetryEventRecord],
) -> dict[int, float]:
    """Waste Cost per Location (CONTEXT-brasaland.md 'KPIs to Measure'):
    sum of stock_waste_registered costs for the week, per location. Same
    skip/default rules as compute_purchase_cost_per_location above.
    """
    totals: dict[int, float] = defaultdict(float)
    for event in events:
        if event.event_type != "stock_waste_registered":
            continue
        tags = event.tags or {}
        location_id = tags.get("location_id")
        if location_id is None:
            continue
        unit_cost = tags.get("unit_cost")
        if unit_cost is None:
            continue
        totals[location_id] += unit_cost * tags.get("quantity", 0)
    return dict(totals)


@task(name="compute-waste-ratio")
def compute_waste_ratio(
    purchase_cost_by_location: dict[int, float],
    waste_cost_by_location: dict[int, float],
) -> dict[int, float]:
    """Waste Ratio (CONTEXT-brasaland.md 'KPIs to Measure'): waste cost
    as a share of purchase cost, per location -- 0 if no purchases that
    week (defined that way explicitly in CONTEXT-brasaland.md section 4,
    not an incidental edge case picked here). Computed for the union of
    both inputs' location_ids, so a location with waste but zero
    purchases that week still gets a ratio (0, per the definition)
    instead of being silently dropped.
    """
    ratios: dict[int, float] = {}
    for location_id in set(purchase_cost_by_location) | set(waste_cost_by_location):
        purchase_cost = purchase_cost_by_location.get(location_id, 0.0)
        waste_cost = waste_cost_by_location.get(location_id, 0.0)
        ratios[location_id] = (waste_cost / purchase_cost) if purchase_cost else 0.0
    return ratios


@task(name="compute-stockout-frequency")
def compute_stockout_frequency(events: list[TelemetryEventRecord]) -> dict[int, int]:
    """Stockout Frequency (CONTEXT-brasaland.md 'KPIs to Measure'): count
    of stock_threshold_triggered events for the week, per location.
    """
    counts: dict[int, int] = defaultdict(int)
    for event in events:
        if event.event_type != "stock_threshold_triggered":
            continue
        location_id = (event.tags or {}).get("location_id")
        if location_id is None:
            continue
        counts[location_id] += 1
    return dict(counts)


@task(name="compute-price-alert-frequency")
def compute_price_alert_frequency(events: list[TelemetryEventRecord]) -> dict[int, int]:
    """Price Alert Frequency (CONTEXT-brasaland.md 'KPIs to Measure'):
    count of ingredient_price_variance_detected events for the week, per
    location.
    """
    counts: dict[int, int] = defaultdict(int)
    for event in events:
        if event.event_type != "ingredient_price_variance_detected":
            continue
        location_id = (event.tags or {}).get("location_id")
        if location_id is None:
            continue
        counts[location_id] += 1
    return dict(counts)


@task(name="assemble-weekly-location-performance-rows")
def assemble_weekly_location_performance_rows(
    purchase_cost_by_location: dict[int, float],
    waste_cost_by_location: dict[int, float],
    waste_ratio_by_location: dict[int, float],
    stockout_frequency_by_location: dict[int, int],
    price_alert_frequency_by_location: dict[int, int],
    week_start: date,
) -> tuple[list[dict], list[int]]:
    """Joins the five per-KPI dicts against LOCATION_REGISTRY and builds
    rows shaped exactly for reporting.weekly_location_performance
    (CONTEXT-brasaland.md section 5). A location appears if it shows up
    in ANY of the five inputs -- e.g. a location with a stockout but no
    purchases that week still gets a row. Returns (rows, unmatched):
    unmatched are location_ids with no entry in LOCATION_REGISTRY,
    skipped here rather than written with a guessed currency -- see
    PIPELINE_DESIGN.md's Schema prerequisite #2.
    """
    all_location_ids = (
        set(purchase_cost_by_location)
        | set(waste_cost_by_location)
        | set(waste_ratio_by_location)
        | set(stockout_frequency_by_location)
        | set(price_alert_frequency_by_location)
    )

    rows: list[dict] = []
    unmatched_location_ids: list[int] = []

    for location_id in all_location_ids:
        country = LOCATION_REGISTRY.get(location_id)
        if country is None:
            unmatched_location_ids.append(location_id)
            continue
        rows.append(
            {
                # Destination column is `text not null`
                # (CONTEXT-brasaland.md section 5); telemetry's own
                # location_id is an integer -- cast at the boundary.
                "location_id": str(location_id),
                "country": country,
                "week_start": week_start,
                "total_purchase_cost": round(purchase_cost_by_location.get(location_id, 0.0), 2),
                "total_waste_cost": round(waste_cost_by_location.get(location_id, 0.0), 2),
                "waste_ratio": round(waste_ratio_by_location.get(location_id, 0.0), 4),
                "stockout_events_count": stockout_frequency_by_location.get(location_id, 0),
                "price_alert_events_count": price_alert_frequency_by_location.get(location_id, 0),
                "currency": CURRENCY_BY_COUNTRY[country],
            }
        )

    return rows, unmatched_location_ids


@flow(name="transform-weekly-location-performance")
def transform_weekly_location_performance_flow(
    events: list[TelemetryEventRecord], week_start: date
) -> tuple[list[dict], list[int]]:
    """Transformation subflow -- Part 3's required second stage. Computes
    each of the five KPIs from CONTEXT-brasaland.md's "KPIs to Measure"
    section as its own task, then assembles them into destination-table
    rows. Explicit inputs (events, week_start), explicit output
    (rows, unmatched) -- no shared state with the extraction or load
    subflows beyond what's passed between them.
    """
    purchase_cost_by_location = compute_purchase_cost_per_location(events)
    waste_cost_by_location = compute_waste_cost_per_location(events)
    waste_ratio_by_location = compute_waste_ratio(purchase_cost_by_location, waste_cost_by_location)
    stockout_frequency_by_location = compute_stockout_frequency(events)
    price_alert_frequency_by_location = compute_price_alert_frequency(events)

    return assemble_weekly_location_performance_rows(
        purchase_cost_by_location,
        waste_cost_by_location,
        waste_ratio_by_location,
        stockout_frequency_by_location,
        price_alert_frequency_by_location,
        week_start,
    )


# ---------------------------------------------------------------------
# Optional step -- flags location_ids with no LOCATION_REGISTRY entry.
# Its own subflow per the Part 3 brief ("if you have optional steps...
# extract them as subflows too and invoke them with return_state=True").
# ---------------------------------------------------------------------


@task(name="write-validation-snapshot")
def write_validation_snapshot(unmatched_location_ids: list[int], week_start: date) -> None:
    """Non-critical: writes any location_ids seen this week but missing
    from LOCATION_REGISTRY to data/eval/, so a registry gap is visible in
    version control instead of silently-skipped rows.
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


@flow(name="flag-unmatched-locations")
def flag_unmatched_locations_flow(unmatched_location_ids: list[int], week_start: date) -> None:
    """Optional subflow. Invoked with return_state=True from the main
    flow, so a failure here (e.g. a disk/permissions problem) is logged
    and never stops the actual report from loading -- same non-critical
    treatment this step had as a single task in Part 2.
    """
    write_validation_snapshot(unmatched_location_ids, week_start)


# ---------------------------------------------------------------------
# Load -- one task (Supabase-facing, retrying), one subflow.
# ---------------------------------------------------------------------


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


@flow(name="load-weekly-location-performance")
def load_weekly_location_performance_flow(rows: list[dict]) -> int:
    """Load subflow -- Part 3's required third stage. Thin wrapper
    around the retrying, upserting task above.
    """
    return load_weekly_performance(rows)


# ---------------------------------------------------------------------
# Run-log bookkeeping. Not one of the three ETL stages, so these stay as
# plain functions rather than tasks/subflows -- forcing pipeline_runs
# writes into that shape would add orchestration overhead for no benefit,
# since they're simple, fast, single-row writes with nothing to retry or
# cache independently of the flow run they belong to.
# ---------------------------------------------------------------------


def _find_running_run_for_week(week_start: date) -> Optional[str]:
    """Concurrency guard -- PIPELINE_DESIGN.md's Cross-cutting §1
    (concurrent runs) flagged that the weekly schedule and a manual
    trigger could overlap on the same week_start; the last upsert to win
    wouldn't be a correctness bug (same source data), but two
    "Completed" log rows for one week is confusing to read. That design
    doc originally proposed a Prefect concurrency-limit tag for this, but
    this pipeline runs against Prefect's own ephemeral local server (no
    persistent Prefect Cloud/Server available here), where a registered
    concurrency limit wouldn't reliably persist between runs. Checking
    pipeline_runs itself -- the same table already used for the
    execution log -- accomplishes the same goal without that dependency.
    """
    with Session(engine) as db:
        return db.exec(
            select(PipelineRun.run_id).where(
                PipelineRun.week_start == week_start,
                PipelineRun.status == "Running",
            )
        ).first()


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


# ---------------------------------------------------------------------
# Main flow -- coordinates the subflows above. No ETL logic of its own.
# ---------------------------------------------------------------------


@flow(name="weekly-location-performance")
def weekly_location_performance_flow(
    week_start: Optional[date] = None, triggered_by: str = "manual"
) -> dict:
    """Main flow -- calls the extraction, transformation, and load
    subflows in sequence, plus the optional flag-unmatched-locations
    subflow. Contains no ETL logic itself: only orchestration, the
    concurrency guard, and run-log bookkeeping.

    Wraps the whole body in try/except so ANY unhandled failure --
    including one that survives a task's own retries -- still gets
    recorded as reporting.pipeline_runs.status="Failed" with an
    error_message, not just silently dropped. This is on top of, not
    instead of, the per-task retries inside each subflow.
    """
    week_start = week_start or _most_recent_monday()

    existing_run_id = _find_running_run_for_week(week_start)
    if existing_run_id is not None:
        return {
            "run_id": existing_run_id,
            "week_start": week_start.isoformat(),
            "skipped": True,
            "reason": f"a run for {week_start.isoformat()} is already in progress",
        }

    run_id = str(uuid4())
    _write_run_start(run_id, week_start, triggered_by)

    try:
        events = extract_cost_and_waste_events_flow(week_start)
        rows, unmatched_location_ids = transform_weekly_location_performance_flow(
            events, week_start
        )

        # Optional/non-critical subflow, invoked with return_state=True so
        # a failure here is logged and the flow keeps going rather than
        # crashing the whole run -- see the Part 2 resilience ticket's
        # "tolerate partial failures" requirement, carried forward.
        snapshot_state = flag_unmatched_locations_flow(
            unmatched_location_ids, week_start, return_state=True
        )
        if snapshot_state.is_failed():
            print(f"[pipeline] validation snapshot failed (non-critical): {snapshot_state}")

        locations_written = load_weekly_location_performance_flow(rows)
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
