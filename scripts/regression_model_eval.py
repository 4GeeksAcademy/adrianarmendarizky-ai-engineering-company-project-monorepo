"""
scripts/regression_model_eval.py -- Technical evaluation of the sales
forecasting model built in scripts/sales_forecast_train.py.

A trained model isn't automatically a trustworthy one. This script
answers the tech lead's ticket: is the Random Forest from the last
milestone underfitting, overfitting, or reasonably well fitted, and is
its performance stable across different slices of the training data?
Everything here operates ONLY on the training period (2016-2023) --
the 2024-2025 test set stays untouched, exactly like in the previous
milestone, so it's still a fair final check later.

Business framing (MAE vs. RMSE) -- a note on context-time-series.md
----------------------------------------------------------------------
The ticket says to read CONTEXT-company.md to see which error is more
costly for Brasaland -- overestimating sales or underestimating them
-- and justify the choice of primary metric from that. I re-read
context-time-series.md end to end and it does NOT state this directly
anywhere (checked again after being asked to). The justification below
is my own reasoning from the one relevant fact the doc does give
(section 1: Felipe's ingredient purchasing and Lucia's meat-volume
procurement both depend on this forecast, and meat is perishable) --
not something quoted or paraphrased from the document. Worth flagging
to your tech lead/instructor that the promised cost framing isn't
actually in this file.

Usage:
    uv run python scripts/regression_model_eval.py
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sales_forecast_train import (  # noqa: E402
    DATA_PATH,
    FEATURE_COLUMNS,
    RANDOM_STATE,
    TARGET_COLUMN,
    build_features,
    load_consolidated_sales,
    split_train_test,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data" / "eval"
N_SPLITS = 5


def build_estimator() -> RandomForestRegressor:
    """Same hyperparameters as scripts/sales_forecast_train.py's
    train_model() -- this evaluates the model that was actually
    shipped, not a re-tuned one.
    """
    return RandomForestRegressor(
        n_estimators=300,
        max_depth=6,
        min_samples_leaf=2,
        random_state=RANDOM_STATE,
    )


# ---------------------------------------------------------------------------
# Time-aware cross-validation
# ---------------------------------------------------------------------------

def get_cv_folds(n_rows: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """The raw TimeSeriesSplit fold indices, with no model fitting --
    kept separate from run_temporal_cross_validation() so the fold
    ordering itself can be unit-tested quickly, and reused by both
    tests/pipelines/test_temporal_cv_order.py and this script.
    """
    return list(TimeSeriesSplit(n_splits=N_SPLITS).split(np.arange(n_rows)))


def verify_fold_chronology(train_idx: np.ndarray, val_idx: np.ndarray, months: np.ndarray, fold_num: int) -> None:
    """TimeSeriesSplit never shuffles and each fold's validation rows
    all come after that fold's training rows -- but "the library
    doesn't shuffle" isn't proof, so every fold is explicitly checked
    here before its metrics are trusted.
    """
    assert list(train_idx) == sorted(train_idx), f"fold {fold_num}: train indices out of order"
    assert list(val_idx) == sorted(val_idx), f"fold {fold_num}: val indices out of order"
    assert train_idx.max() < val_idx.min(), f"fold {fold_num}: a validation row precedes a training row"
    assert months[train_idx].max() < months[val_idx].min(), f"fold {fold_num}: validation month overlaps or precedes a training month"


def run_temporal_cross_validation(train: pd.DataFrame) -> list[dict]:
    """5-fold TimeSeriesSplit over the training set only."""
    X = train[FEATURE_COLUMNS].to_numpy()
    y = train[TARGET_COLUMN].to_numpy()
    months = train["month"].to_numpy()

    fold_results = []

    for fold_num, (train_idx, val_idx) in enumerate(get_cv_folds(len(train)), start=1):
        verify_fold_chronology(train_idx, val_idx, months, fold_num)

        model = build_estimator()
        model.fit(X[train_idx], y[train_idx])

        train_pred = model.predict(X[train_idx])
        val_pred = model.predict(X[val_idx])

        fold_results.append({
            "fold": fold_num,
            "train_months": int(len(train_idx)),
            "val_months": int(len(val_idx)),
            "train_mae": float(mean_absolute_error(y[train_idx], train_pred)),
            "train_rmse": float(np.sqrt(mean_squared_error(y[train_idx], train_pred))),
            "val_mae": float(mean_absolute_error(y[val_idx], val_pred)),
            "val_rmse": float(np.sqrt(mean_squared_error(y[val_idx], val_pred))),
        })

    return fold_results


def summarize_folds(fold_results: list[dict]) -> dict:
    """Mean +/- standard deviation across folds -- a single aggregate
    number would hide how much the error swings fold to fold, which is
    exactly the "how stable is it" question the ticket asks.
    """
    summary = {}
    for metric in ["train_mae", "train_rmse", "val_mae", "val_rmse"]:
        values = [f[metric] for f in fold_results]
        summary[metric] = {"mean": float(np.mean(values)), "std": float(np.std(values))}
    return summary


# ---------------------------------------------------------------------------
# Learning curve
# ---------------------------------------------------------------------------

def generate_learning_curve(train: pd.DataFrame, save_path: Path) -> dict:
    """Training error and validation error as the training set grows.

    NOT built with sklearn's learning_curve(cv=TimeSeriesSplit(...)):
    that combination silently caps the training size at whatever the
    SMALLEST fold's training set happens to be (14 months here, out of
    84 available) -- because every requested size has to be valid for
    every fold simultaneously. The resulting curve only ever showed
    4-14 training months, which is too little data to diagnose
    anything and made every validation error look far worse than the
    model's real, 5-fold-averaged behavior.

    Instead: hold out the most recent 14 months of the training period
    as a single fixed validation window (matching one TimeSeriesSplit
    fold's size), and re-train on an expanding prefix of the 70 months
    before it -- 1 year, 2 years, and so on up to all 70 -- so the
    curve actually reaches a realistic training size.
    """
    validation = train.iloc[-14:]
    pool = train.iloc[:-14]  # 70 months available to train on, all strictly before the validation window

    X_val = validation[FEATURE_COLUMNS].to_numpy()
    y_val = validation[TARGET_COLUMN].to_numpy()

    sizes = [s for s in [12, 24, 36, 48, 60, len(pool)] if s <= len(pool)]
    train_mae, val_mae = [], []

    for size in sizes:
        subset = pool.iloc[:size]  # expanding window, always starting from the earliest month
        X_train = subset[FEATURE_COLUMNS].to_numpy()
        y_train = subset[TARGET_COLUMN].to_numpy()

        model = build_estimator()
        model.fit(X_train, y_train)

        train_mae.append(mean_absolute_error(y_train, model.predict(X_train)))
        val_mae.append(mean_absolute_error(y_val, model.predict(X_val)))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(sizes, train_mae, "o-", color="#16a34a", label="Training error (MAE)")
    ax.plot(sizes, val_mae, "o-", color="#dc2626", label="Validation error (MAE, fixed last-14-month window)")
    ax.set_xlabel("Training examples (months, expanding from 2017-01)")
    ax.set_ylabel("MAE (USD)")
    ax.set_title("Learning curve -- Brasaland sales forecast (Random Forest)")
    ax.legend()
    fig.tight_layout()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150)
    plt.close(fig)

    return {
        "train_sizes": sizes,
        "train_mae_mean": train_mae,
        "val_mae_mean": val_mae,
    }


def diagnose_fit(cv_summary: dict, learning_curve_data: dict) -> dict:
    """Primary diagnosis comes from the 5-fold CV summary (averaged
    over all 5 folds, not just one noisy point) -- how "high" each
    error is gets judged relative to average monthly revenue, so it
    means something concrete rather than a bare dollar figure. The
    learning curve is used only to check whether the train/val gap
    narrows as training data grows (the tell for "more data would
    help") or stays wide throughout (the tell that it won't).
    """
    train_mae = cv_summary["train_mae"]["mean"]
    val_mae = cv_summary["val_mae"]["mean"]
    gap = val_mae - train_mae
    gap_pct_of_val = gap / val_mae * 100

    lc_gap_first = learning_curve_data["val_mae_mean"][0] - learning_curve_data["train_mae_mean"][0]
    lc_gap_last = learning_curve_data["val_mae_mean"][-1] - learning_curve_data["train_mae_mean"][-1]
    gap_narrowing = lc_gap_last < lc_gap_first * 0.8  # shrunk by at least 20% as data grew

    if train_mae > 0.08 * AVG_REVENUE and val_mae > 0.08 * AVG_REVENUE and gap_pct_of_val < 25:
        diagnosis = "underfitting"
    elif gap_pct_of_val >= 25:
        diagnosis = "overfitting"
    else:
        diagnosis = "well_fitted"

    return {
        "cv_train_mae": train_mae,
        "cv_val_mae": val_mae,
        "gap_usd": gap,
        "gap_pct_of_val_error": gap_pct_of_val,
        "gap_narrowing_with_more_data": gap_narrowing,
        "diagnosis": diagnosis,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

AVG_REVENUE = None  # set in main() once the data is loaded


def main() -> None:
    global AVG_REVENUE

    raw = load_consolidated_sales(DATA_PATH)
    features_df = build_features(raw)
    train, _test = split_train_test(features_df)  # test set is untouched here, on purpose
    AVG_REVENUE = float(train[TARGET_COLUMN].mean())

    fold_results = run_temporal_cross_validation(train)
    summary = summarize_folds(fold_results)

    lc_data = generate_learning_curve(train, OUTPUT_DIR / "learning_curve.png")
    diagnosis = diagnose_fit(summary, lc_data)

    output = {
        "n_splits": N_SPLITS,
        "avg_monthly_revenue_usd": AVG_REVENUE,
        "fold_results": fold_results,
        "cv_summary_mean_std": summary,
        "learning_curve": lc_data,
        "diagnosis": diagnosis,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "cv_metrics.json", "w") as f:
        json.dump(output, f, indent=2)

    print(json.dumps({"cv_summary_mean_std": summary, "diagnosis": diagnosis}, indent=2))
    print(f"\nSaved learning curve to {OUTPUT_DIR / 'learning_curve.png'}")
    print(f"Saved CV metrics to {OUTPUT_DIR / 'cv_metrics.json'}")


if __name__ == "__main__":
    main()
