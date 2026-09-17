"""
tests/pipelines/test_sales_forecast_split.py -- unit tests for
scripts/sales_forecast_train.py's train/test split and feature
engineering.

context-time-series.md section 6 requires "a unit test... validating the
8/2-year split" -- these tests check both halves of that: that the
split lands on the right months, AND that no feature is built from a
future row (the ticket's other requirement, "no leakage from future
rows"), since a wrong split date wouldn't catch a leaky feature and
vice versa.

Uses the real data/raw/brasaland_sales.csv, not synthetic data: the
dataset is generated with a fixed random_state=42 (context-time-series.md
section 4), so it's deterministic -- these exact row counts and
boundary dates will hold every time the file is regenerated the same
way.

Run with:
    uv run python -m pytest tests/pipelines/test_sales_forecast_split.py -v
"""

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sales_forecast_train as sft  # noqa: E402


# ---------------------------------------------------------------------
# The 8/2-year split itself
# ---------------------------------------------------------------------

def _load_features():
    raw = sft.load_consolidated_sales(sft.DATA_PATH)
    return sft.build_features(raw)


def test_train_covers_only_2016_through_2023():
    train, _ = sft.split_train_test(_load_features())
    assert train["month"].min() >= pd.Timestamp("2016-01-01")
    assert train["month"].max() <= pd.Timestamp("2023-12-01")


def test_test_covers_exactly_the_24_months_of_2024_and_2025():
    _, test = sft.split_train_test(_load_features())
    assert test["month"].min() == pd.Timestamp("2024-01-01")
    assert test["month"].max() == pd.Timestamp("2025-12-01")
    assert len(test) == 24


def test_no_month_appears_in_both_train_and_test():
    train, test = sft.split_train_test(_load_features())
    overlap = set(train["month"]) & set(test["month"])
    assert overlap == set()


def test_test_rows_have_every_feature_populated():
    """The ticket's "no missing months" and "no leakage" requirements
    both fail silently as NaNs -- if any crept in, this would catch it
    before it reached the model.
    """
    _, test = sft.split_train_test(_load_features())
    assert test[sft.FEATURE_COLUMNS].isnull().sum().sum() == 0


# ---------------------------------------------------------------------
# No leakage from future rows
# ---------------------------------------------------------------------

def test_lag_and_rolling_features_never_see_the_current_or_a_future_month():
    """Builds a tiny 14-month series of distinct, easy-to-check values
    (100, 101, 102, ...) and hand-verifies every feature for the LAST
    row -- if any feature used the current month's own value or a
    later one, the numbers below would be wrong.
    """
    months = pd.date_range("2020-01-01", periods=14, freq="MS")
    revenue = [100.0 + i for i in range(14)]  # 100, 101, ..., 113
    df = pd.DataFrame({"month": months, sft.TARGET_COLUMN: revenue})

    features = sft.build_features(df)
    last = features.iloc[-1]  # month 2021-02-01, revenue_usd = 113

    assert last["lag_1"] == 112.0   # previous month only
    assert last["lag_2"] == 111.0
    assert last["lag_3"] == 110.0
    assert last["lag_12"] == 101.0  # same month, one year earlier

    # rolling_mean_3 over the 3 months strictly before this one: 111,112 and
    # the month before that (110) -- i.e. months 11,12,13 (0-indexed values
    # 110,111,112), never 113 (the current month) itself.
    assert last["rolling_mean_3"] == sum([110.0, 111.0, 112.0]) / 3

    assert last["time_index"] == 13  # 0-indexed position, informational only


def test_first_row_has_no_lag_or_rolling_features_available():
    """The very first month in the whole series has no history at all
    behind it -- every lag/rolling feature must be NaN, not some
    silently-wrong fallback value.
    """
    months = pd.date_range("2020-01-01", periods=3, freq="MS")
    df = pd.DataFrame({"month": months, sft.TARGET_COLUMN: [100.0, 101.0, 102.0]})

    features = sft.build_features(df)
    first = features.iloc[0]

    assert pd.isna(first["lag_1"])
    assert pd.isna(first["rolling_mean_3"])


# ---------------------------------------------------------------------
# Data validation (context-time-series.md section 5 business constraints)
# ---------------------------------------------------------------------

def test_load_raises_on_a_missing_month(tmp_path):
    """"There must be no missing months in the 2016-01 to 2025-12
    range" -- a gap should fail loudly at load time, not train
    silently on a shorter series.
    """
    months = ["2020-01-01", "2020-02-01", "2020-04-01"]  # March is missing
    csv_path = tmp_path / "gap_sales.csv"
    pd.DataFrame({
        "month": months,
        "revenue_usd": [100.0, 101.0, 102.0],
        "covers_served": [10, 11, 12],
        "avg_ticket_usd": [10.0, 10.0, 10.0],
        "market": ["consolidated"] * 3,
    }).to_csv(csv_path, index=False)

    try:
        sft.load_consolidated_sales(csv_path)
        assert False, "expected a ValueError for the missing month"
    except ValueError as exc:
        assert "Missing months" in str(exc)


def test_load_raises_on_non_positive_revenue(tmp_path):
    """"All revenue_usd values must be positive" -- a zero or negative
    row should fail loudly rather than silently entering training.
    """
    csv_path = tmp_path / "bad_sales.csv"
    pd.DataFrame({
        "month": ["2020-01-01", "2020-02-01"],
        "revenue_usd": [100.0, 0.0],
        "covers_served": [10, 11],
        "avg_ticket_usd": [10.0, 0.0],
        "market": ["consolidated"] * 2,
    }).to_csv(csv_path, index=False)

    try:
        sft.load_consolidated_sales(csv_path)
        assert False, "expected a ValueError for non-positive revenue"
    except ValueError as exc:
        assert "positive" in str(exc)
