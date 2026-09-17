"""
scripts/sales_forecast_train.py -- Sales Forecasting with a Regression Model

Trains a regression model on Brasaland's 10 years of consolidated monthly
sales (data/raw/brasaland_sales.csv) to answer Finance's RFI: can revenue
for the coming months be predicted within an acceptable margin of error,
before committing to a full executive dashboard? See context-time-series.md
for the full business context, the data dictionary, and the growth /
seasonality pattern already baked into the dataset.

Why Random Forest, not XGBoost
-------------------------------
Both are valid choices for this ticket; this script uses Random Forest
because of what the stakeholder actually asked for. Mariana needs a
number she can explain to Finance "without it sounding like a black
box" -- Random Forest's feature_importances_ are simple to read out
loud in a meeting, and each tree is an individually readable decision
path. It also needs little tuning, which matters here: there are only
~84-96 monthly rows to train on (8 years), and a heavily-tuned XGBoost
model has more room to overfit that small a dataset than to add real
accuracy. XGBoost would be the better call if the priority were
squeezing out the last bit of accuracy for a technical audience.

Why covers_served and avg_ticket_usd are NOT input features
-------------------------------------------------------------
revenue_usd ~= covers_served * avg_ticket_usd for every row in this
dataset (they differ by rounding only, well under 0.01%). Feeding a
model the same month's covers_served and avg_ticket_usd to predict
that month's revenue_usd wouldn't be forecasting anything -- it would
just be recovering the target from a near-identity. context-time-series.md
section 2 is explicit that revenue_usd is the target; this script builds
every feature from revenue_usd's OWN history (lags, rolling stats) plus
the calendar, never from another same-month column.

One-step-ahead evaluation, not a recursive forecast
-----------------------------------------------------
Every lag / rolling-window feature for a given month is built only from
*actual* revenue in strictly earlier months (see build_features) -- never
the same month or a later one, so there's no leakage from future rows.
That includes test-period rows: a test row's lag features can reach back
into the training period's real numbers, the same way a person
forecasting March 2024 in real life already knows the real January and
February 2024 numbers. That's a legitimate one-step-ahead forecast, not
a leak -- it does mean the model isn't being asked to project 24 months
into the future from a single starting point (a harder, recursive
problem where errors compound on themselves); that's a natural next
iteration once this first model is validated.

Metrics -- what "K2 Score" is being reported as
--------------------------------------------------
The ticket asks for MSE, PSI, Gini, and "K2 Score." MSE and PSI are
standard; "K2 Score" isn't a term with a fixed definition. Given it's
listed alongside Gini and PSI -- the two metrics almost always reported
together with the Kolmogorov-Smirnov (KS) statistic in this style of
"can the model tell good months from bad months apart" evaluation --
this script reports it as the KS statistic (the two-sample
Kolmogorov-Smirnov test is sometimes literally written "K-S 2-sample,"
which is likely where "K2" comes from). Worth confirming with your tech
lead/instructor if that's not what was taught.

Usage:
    uv run python scripts/sales_forecast_train.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, roc_auc_score

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "raw" / "brasaland_sales.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "eval" / "sales-forecast"

TRAIN_TEST_SPLIT_DATE = pd.Timestamp("2024-01-01")  # first 8 years train, last 2 test
RANDOM_STATE = 42

FEATURE_COLUMNS = [
    "lag_1", "lag_2", "lag_3", "lag_12",
    "rolling_mean_3", "rolling_std_3", "rolling_mean_12",
    "month_num", "quarter", "is_january", "is_december",
    "time_index",
]
TARGET_COLUMN = "revenue_usd"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_consolidated_sales(csv_path: Path) -> pd.DataFrame:
    """Loads the consolidated row per month, sorted and validated.

    context-time-series.md section 5: "There must be no missing months in
    the 2016-01 to 2025-12 range" -- checked here rather than assumed.
    """
    df = pd.read_csv(csv_path)
    df = df[df["market"] == "consolidated"].copy()
    df["month"] = pd.to_datetime(df["month"])
    df = df.sort_values("month").reset_index(drop=True)

    expected_months = pd.date_range(df["month"].min(), df["month"].max(), freq="MS")
    missing = expected_months.difference(df["month"])
    if len(missing) > 0:
        raise ValueError(f"Missing months in dataset: {list(missing)}")

    if (df[TARGET_COLUMN] <= 0).any():
        raise ValueError("revenue_usd must be positive for every row (context-time-series.md section 5).")

    return df[["month", TARGET_COLUMN]]


# ---------------------------------------------------------------------------
# Feature engineering (causal only -- see module docstring)
# ---------------------------------------------------------------------------

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds lag, rolling-window, and calendar features to a
    month-sorted, single-column (revenue_usd) dataframe.

    Every rolling/lag value is shifted so that the row for month M only
    ever sees revenue from month M-1 or earlier -- .shift(1) before
    .rolling() is what guarantees that, not just the lag columns
    themselves.
    """
    out = df.copy()

    out["lag_1"] = out[TARGET_COLUMN].shift(1)
    out["lag_2"] = out[TARGET_COLUMN].shift(2)
    out["lag_3"] = out[TARGET_COLUMN].shift(3)
    out["lag_12"] = out[TARGET_COLUMN].shift(12)  # same month, prior year

    shifted = out[TARGET_COLUMN].shift(1)  # never include month M itself
    out["rolling_mean_3"] = shifted.rolling(window=3).mean()
    out["rolling_std_3"] = shifted.rolling(window=3).std()
    out["rolling_mean_12"] = shifted.rolling(window=12).mean()

    out["month_num"] = out["month"].dt.month
    out["quarter"] = out["month"].dt.quarter
    out["is_january"] = (out["month_num"] == 1).astype(int)
    out["is_december"] = (out["month_num"] == 12).astype(int)
    out["time_index"] = np.arange(len(out))  # captures the overall growth trend

    return out


def split_train_test(features_df: pd.DataFrame):
    """First 8 years (2016-01 to 2023-12) train, last 2 years
    (2024-01 to 2025-12) test -- per context-time-series.md section 6.

    Rows whose lag_12 / rolling_mean_12 aren't available yet (the first
    12 months of the whole series) are dropped from TRAIN only, never
    from test -- by the time the test period starts, 12 full months of
    real history already exist behind every row.
    """
    train = features_df[features_df["month"] < TRAIN_TEST_SPLIT_DATE].dropna(subset=FEATURE_COLUMNS)
    test = features_df[features_df["month"] >= TRAIN_TEST_SPLIT_DATE].copy()
    assert test[FEATURE_COLUMNS].isnull().sum().sum() == 0, "test rows must have every feature populated"
    return train, test


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def train_model(train: pd.DataFrame) -> RandomForestRegressor:
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=2,
        random_state=RANDOM_STATE,
    )
    model.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])
    return model


def predict_with_range(model: RandomForestRegressor, X: pd.DataFrame):
    """Point prediction plus a variability range built from the spread
    of the individual trees in the forest (5th-95th percentile) --
    a Random Forest's natural substitute for a formal prediction
    interval, and a very tangible way to show Mariana "not a single
    optimistic number" per the ticket.
    """
    X_values = X.to_numpy() if hasattr(X, "to_numpy") else X
    per_tree = np.stack([tree.predict(X_values) for tree in model.estimators_])
    point = model.predict(X)
    lower = np.percentile(per_tree, 5, axis=0)
    upper = np.percentile(per_tree, 95, axis=0)
    return point, lower, upper


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_mse_and_mape(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"mse_usd2": float(mse), "rmse_usd": float(np.sqrt(mse)), "mape_pct": mape}


def compute_psi(train_scores: np.ndarray, test_scores: np.ndarray, buckets: int = 5) -> float:
    """Population Stability Index between the model's predictions on
    train vs. test. Bucket edges come from TRAIN's quantiles (the
    "expected"/reference population); test is the "actual" population
    being compared against it. 5 buckets rather than the textbook 10 --
    with only 24 test months, 10 buckets would average ~2.4 rows each,
    too thin to be a stable read.
    """
    edges = np.quantile(train_scores, np.linspace(0, 1, buckets + 1))
    edges[0], edges[-1] = -np.inf, np.inf  # catch any test value outside train's observed range

    train_counts, _ = np.histogram(train_scores, bins=edges)
    test_counts, _ = np.histogram(test_scores, bins=edges)

    train_pct = np.clip(train_counts / train_counts.sum(), 1e-4, None)
    test_pct = np.clip(test_counts / test_counts.sum(), 1e-4, None)

    return float(np.sum((test_pct - train_pct) * np.log(test_pct / train_pct)))


def compute_discrimination_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Gini and KS ("K2 Score" -- see module docstring), both measuring
    the same thing Mariana cares about: can the model's ranking tell a
    good month from a bad one? "Good month" = actual revenue at or
    above the test period's own median, splitting the 24 test months
    into two balanced groups of 12.
    """
    median = np.median(y_true)
    is_good = y_true >= median

    auc = roc_auc_score(is_good, y_pred)
    gini = 2 * auc - 1
    ks_stat = ks_2samp(y_pred[is_good], y_pred[~is_good]).statistic

    return {"gini": float(gini), "ks_score": float(ks_stat), "auc": float(auc)}


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def plot_predictions(test: pd.DataFrame, y_pred: np.ndarray, lower: np.ndarray, upper: np.ndarray, save_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(test["month"], test[TARGET_COLUMN], label="Actual", color="#1f2937", marker="o")
    ax.plot(test["month"], y_pred, label="Predicted", color="#2563eb", marker="o")
    ax.fill_between(test["month"], lower, upper, color="#2563eb", alpha=0.15, label="5th-95th percentile range")
    ax.set_title("Brasaland consolidated revenue -- predicted vs. actual (2024-2025 test years)")
    ax.set_ylabel("Revenue (USD)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    raw = load_consolidated_sales(DATA_PATH)
    features_df = build_features(raw)
    train, test = split_train_test(features_df)

    model = train_model(train)

    train_pred, _, _ = predict_with_range(model, train[FEATURE_COLUMNS])
    test_pred, test_lower, test_upper = predict_with_range(model, test[FEATURE_COLUMNS])

    metrics = {}
    metrics.update(compute_mse_and_mape(test[TARGET_COLUMN].to_numpy(), test_pred))
    metrics["psi"] = compute_psi(train_pred, test_pred)
    metrics.update(compute_discrimination_metrics(test[TARGET_COLUMN].to_numpy(), test_pred))
    metrics["train_rows"] = int(len(train))
    metrics["test_rows"] = int(len(test))
    metrics["feature_importances"] = dict(
        sorted(zip(FEATURE_COLUMNS, model.feature_importances_.round(4).tolist()), key=lambda kv: -kv[1])
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    plot_predictions(test, test_pred, test_lower, test_upper, OUTPUT_DIR / "prediction_vs_actual.png")

    print(json.dumps(metrics, indent=2))
    if metrics["psi"] > 0.25:  # 0.25 is the conventional "significant shift" threshold
        print(
            f"\nPSI = {metrics['psi']:.2f} is far above the usual 0.25 'significant shift' "
            "threshold: essentially none of the test period's predictions overlap the "
            "train period's distribution. Per context-time-series.md section 3, this is the "
            "expected signature of the dataset's real ~5-7%/year compounding growth (test "
            "years are simply a higher-revenue era than most of train) rather than a sign "
            "the model is unstable -- worth stating explicitly in the PR description, as "
            "the ticket asks."
        )
    print(f"\nSaved plot to {OUTPUT_DIR / 'prediction_vs_actual.png'}")
    print(f"Saved metrics to {OUTPUT_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
