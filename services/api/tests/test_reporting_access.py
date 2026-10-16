"""Login requirements on reporting, task-status and telemetry-report routes
(OWASP A01). Written before the fix. The database, the task queue and the
telemetry analysis are replaced by fakes, so nothing real is touched and no
pipeline run is started."""
import types

import pytest

import routes.reporting as reporting_routes
import routes.tasks as tasks_routes
import routes.telemetry as telemetry_routes
from database import get_db
from main import app


class _FakeResult:
    def all(self):
        return []

    def first(self):
        return None


class _FakeDB:
    def exec(self, *args, **kwargs):
        return _FakeResult()


class _FakeAsyncResult:
    state = "PENDING"
    result = None

    def __init__(self, task_id, app=None):
        self.id = task_id


class _FakeTask:
    id = "fake-task-id"


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    queued = []
    monkeypatch.setattr(
        reporting_routes,
        "run_weekly_performance_report",
        types.SimpleNamespace(delay=lambda **kwargs: queued.append(kwargs) or _FakeTask()),
    )
    monkeypatch.setattr(tasks_routes, "AsyncResult", _FakeAsyncResult)
    empty = lambda *args, **kwargs: {}
    monkeypatch.setattr(
        telemetry_routes,
        "telemetry_analysis",
        types.SimpleNamespace(
            events_per_day=empty,
            events_by_type_per_day=empty,
            api_error_rate_per_day=empty,
            api_latency_avg_ms_per_day=empty,
            auth_failure_rate_per_day=empty,
        ),
    )
    telemetry_routes._report_cache.clear()
    yield queued
    app.dependency_overrides.pop(get_db, None)


def test_no_login_cannot_read_the_weekly_report(client):
    assert client.get("/reporting/weekly-location-performance").status_code == 401


def test_no_login_cannot_read_the_latest_pipeline_run(client):
    assert client.get("/reporting/pipeline-runs/latest").status_code == 401


def test_no_login_cannot_start_a_pipeline_run(client, fakes):
    assert client.post("/reporting/pipeline-runs").status_code == 401
    assert fakes == []  # nothing was queued


def test_no_login_cannot_read_task_status(client):
    assert client.get("/tasks/abc").status_code == 401


def test_no_login_cannot_read_the_telemetry_report(client):
    assert client.get("/telemetry/report").status_code == 401


def test_a_logged_in_user_can_still_use_all_of_them(client, register_and_login, fakes):
    headers = register_and_login(email="user@example.com")["headers"]
    assert client.get("/reporting/weekly-location-performance", headers=headers).status_code == 200
    assert client.get("/reporting/pipeline-runs/latest", headers=headers).status_code == 200
    assert client.post("/reporting/pipeline-runs", headers=headers).status_code == 202
    assert fakes == [{"week_start": None, "triggered_by": "async"}]
    assert client.get("/tasks/abc", headers=headers).status_code == 200
    assert client.get("/telemetry/report", headers=headers).status_code == 200


def test_telemetry_events_stay_open_without_login(client):
    # Deliberate: user_login_failed fires before a token exists.
    assert client.post("/telemetry/events", json={"events": []}).status_code == 200
