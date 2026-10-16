"""Shared test setup for everything in tests/pipelines/."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

import rate_limit  # noqa: E402


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Every test starts with a clean rate limit, so one test's messages
    never count against the next test's fake user."""
    rate_limit.reset()
    yield
    rate_limit.reset()
