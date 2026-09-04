"""
tests/pipelines/test_pipeline.py -- unit tests for the Weekly Location
Cost & Waste Report pipeline's transformation tasks.

Every test here targets a pure function -- no database, no Supabase, no
Prefect orchestration. Each task is called via its underlying `.fn`
(Prefect wraps every @task-decorated function so the original is always
reachable at .fn), which runs the plain Python function directly instead
of going through Prefect's task engine. That's what makes these tests
fast and independent of any live infrastructure -- exactly what Part 3's
"must not depend on a database or external APIs" requirement asks for.

Test data is built with in-memory TelemetryEventRecord instances (see
_make_event below) shaped exactly like the real inbound_order_created /
stock_waste_registered / stock_threshold_triggered /
ingredient_price_variance_detected events described in
CONTEXT-brasaland.md section 3 -- constructing a SQLModel instance this
way never touches a database; it's just a plain Python object.

Run with:
    cd services/api && uv run python -m pytest ../../tests/pipelines/test_pipeline.py -v
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

import pipeline  # noqa: E402
from telemetry_models import TelemetryEventRecord  # noqa: E402


def _make_event(event_type: str, tags: dict) -> TelemetryEventRecord:
    """Builds one in-memory telemetry event for a test -- no database
    involved, this is just constructing a plain Python object with the
    envelope fields every real event has (see telemetry_models.py).
    """
    return TelemetryEventRecord(
        event_id=str(uuid4()),
        timestamp=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        session_id="test-session",
        event_type=event_type,
        schema_version=1,
        tags=tags,
    )


WEEK_START = date(2026, 8, 24)


# ---------------------------------------------------------------------
# Purchase Cost per Location
# ---------------------------------------------------------------------


def test_compute_purchase_cost_per_location_matches_hand_calculation():
    """CONTEXT-brasaland.md: 'sum of inbound_order_created costs for the
    week, in the location's local currency.' Hand-calculated: location 1
    should total (10 * 5.0) + (4 * 2.5) = 60.0; location 8 should total
    3 * 1.0 = 3.0. A stock_waste_registered event with its own unit_cost
    is included in the input to confirm it's correctly ignored -- this
    task only counts inbound_order_created.
    """
    events = [
        _make_event("inbound_order_created", {"location_id": 1, "quantity": 10, "unit_cost": 5.0}),
        _make_event("inbound_order_created", {"location_id": 1, "quantity": 4, "unit_cost": 2.5}),
        _make_event("inbound_order_created", {"location_id": 8, "quantity": 3, "unit_cost": 1.0}),
        _make_event("stock_waste_registered", {"location_id": 1, "quantity": 99, "unit_cost": 99.0}),
    ]

    result = pipeline.compute_purchase_cost_per_location.fn(events)

    assert result == {1: 60.0, 8: 3.0}


def test_compute_purchase_cost_per_location_skips_malformed_events():
    """Defensive behavior: an event with no location_id can't be
    attributed to anywhere, and an event with no unit_cost can't be
    priced -- both should be skipped rather than raising. A tags value
    of None entirely (a malformed event, not just a missing key) must
    also not crash the task. A missing quantity (present unit_cost, no
    quantity key at all) should default to contributing 0, matching
    every other optional telemetry field in this pipeline.
    """
    events = [
        _make_event("inbound_order_created", {"location_id": None, "quantity": 10, "unit_cost": 5.0}),
        _make_event("inbound_order_created", {"location_id": 1, "quantity": 10}),  # no unit_cost
        _make_event("inbound_order_created", {"location_id": 2, "unit_cost": 4.0}),  # no quantity
        TelemetryEventRecord(
            event_id=str(uuid4()),
            timestamp=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
            session_id="test-session",
            event_type="inbound_order_created",
            schema_version=1,
            tags=None,  # malformed: tags itself is null, not just a missing key
        ),
    ]

    result = pipeline.compute_purchase_cost_per_location.fn(events)

    # location 1 skipped (no unit_cost), location None skipped (no
    # location_id), the null-tags event skipped entirely -- only
    # location 2 contributes, and it contributes 0 (missing quantity).
    assert result == {2: 0.0}


# ---------------------------------------------------------------------
# Waste Cost per Location
# ---------------------------------------------------------------------


def test_compute_waste_cost_per_location_matches_hand_calculation():
    """CONTEXT-brasaland.md: 'sum of stock_waste_registered costs for
    the week.' Hand-calculated: location 1 should total 2 * 15.75 = 31.5.
    An inbound_order_created event is included to confirm it's ignored --
    this task only counts stock_waste_registered.
    """
    events = [
        _make_event("stock_waste_registered", {"location_id": 1, "quantity": 2, "unit_cost": 15.75}),
        _make_event("inbound_order_created", {"location_id": 1, "quantity": 50, "unit_cost": 8.0}),
    ]

    result = pipeline.compute_waste_cost_per_location.fn(events)

    assert result == {1: 31.5}


# ---------------------------------------------------------------------
# Waste Ratio
# ---------------------------------------------------------------------


def test_compute_waste_ratio_matches_definition():
    """CONTEXT-brasaland.md: 'waste cost as a share of purchase cost for
    that location and week... 0 if no purchases that week.' Location 1
    has both: 25.0 / 100.0 = 0.25. Location 2 has waste but literally no
    purchase_cost entry at all (not even a 0.0) -- must still resolve to
    0, not raise ZeroDivisionError, per the definition's explicit rule.
    """
    purchase_cost_by_location = {1: 100.0}
    waste_cost_by_location = {1: 25.0, 2: 10.0}

    result = pipeline.compute_waste_ratio.fn(purchase_cost_by_location, waste_cost_by_location)

    assert result == {1: 0.25, 2: 0.0}


# ---------------------------------------------------------------------
# Stockout Frequency
# ---------------------------------------------------------------------


def test_compute_stockout_frequency_counts_correctly():
    """CONTEXT-brasaland.md: 'count of stock_threshold_triggered for the
    week.' Location 1 has 3 events, location 8 has 1. A
    stock_waste_registered event is included to confirm it's ignored.
    """
    events = [
        _make_event("stock_threshold_triggered", {"location_id": 1}),
        _make_event("stock_threshold_triggered", {"location_id": 1}),
        _make_event("stock_threshold_triggered", {"location_id": 1}),
        _make_event("stock_threshold_triggered", {"location_id": 8}),
        _make_event("stock_waste_registered", {"location_id": 1, "quantity": 1, "unit_cost": 1.0}),
    ]

    result = pipeline.compute_stockout_frequency.fn(events)

    assert result == {1: 3, 8: 1}


# ---------------------------------------------------------------------
# Price Alert Frequency
# ---------------------------------------------------------------------


def test_compute_price_alert_frequency_counts_correctly():
    """CONTEXT-brasaland.md: 'count of ingredient_price_variance_detected
    for the week.' Location 1 has 2 events, location 8 has 0.
    """
    events = [
        _make_event("ingredient_price_variance_detected", {"location_id": 1}),
        _make_event("ingredient_price_variance_detected", {"location_id": 1}),
        _make_event("inbound_order_created", {"location_id": 8, "quantity": 1, "unit_cost": 1.0}),
    ]

    result = pipeline.compute_price_alert_frequency.fn(events)

    assert result == {1: 2}


# ---------------------------------------------------------------------
# Assembly -- joins the five KPI dicts into destination-table rows
# ---------------------------------------------------------------------


def test_assemble_weekly_location_performance_rows_builds_correct_shape():
    """Location 1 (in LOCATION_REGISTRY as CO/COP) should get a fully
    populated row matching reporting.weekly_location_performance's
    schema (CONTEXT-brasaland.md section 5) exactly. Location 99 (not in
    LOCATION_REGISTRY) must be skipped from rows and reported in
    unmatched instead -- never written with a guessed currency.
    """
    rows, unmatched = pipeline.assemble_weekly_location_performance_rows.fn(
        purchase_cost_by_location={1: 787.5, 99: 10.0},
        waste_cost_by_location={1: 47.25},
        waste_ratio_by_location={1: 0.06},
        stockout_frequency_by_location={1: 1},
        price_alert_frequency_by_location={},
        week_start=WEEK_START,
    )

    assert unmatched == [99]
    assert len(rows) == 1
    assert rows[0] == {
        "location_id": "1",
        "country": "CO",
        "week_start": WEEK_START,
        "total_purchase_cost": 787.5,
        "total_waste_cost": 47.25,
        "waste_ratio": 0.06,
        "stockout_events_count": 1,
        "price_alert_events_count": 0,
        "currency": "COP",
    }
