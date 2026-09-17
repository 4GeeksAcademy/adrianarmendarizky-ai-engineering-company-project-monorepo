"""
tests/pipelines/test_temporal_cv_order.py -- unit tests for the
time-aware cross-validation folds in scripts/regression_model_eval.py.

The ticket asks for a test validating "that the temporal cross-
validation strategy preserves the chronological order of the data
within each fold (no index from a later fold appears before one from
an earlier fold)". That's really two claims, and both are checked
below separately: (1) within a single fold, every validation row
comes after every training row, and (2) across folds, a later fold's
rows never reach backward in time past an earlier fold's rows.

Run with:
    uv run python -m pytest tests/pipelines/test_temporal_cv_order.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import regression_model_eval as rme  # noqa: E402
import sales_forecast_train as sft  # noqa: E402


def _load_train():
    raw = sft.load_consolidated_sales(sft.DATA_PATH)
    features = sft.build_features(raw)
    train, _test = sft.split_train_test(features)
    return train


# ---------------------------------------------------------------------
# Within a single fold
# ---------------------------------------------------------------------

def test_there_are_at_least_5_folds():
    train = _load_train()
    folds = rme.get_cv_folds(len(train))
    assert len(folds) >= 5


def test_indices_within_each_fold_are_not_shuffled():
    train = _load_train()
    for train_idx, val_idx in rme.get_cv_folds(len(train)):
        assert list(train_idx) == sorted(train_idx)
        assert list(val_idx) == sorted(val_idx)


def test_every_folds_validation_rows_come_after_its_training_rows():
    train = _load_train()
    for fold_num, (train_idx, val_idx) in enumerate(rme.get_cv_folds(len(train)), start=1):
        assert train_idx.max() < val_idx.min(), f"fold {fold_num} mixes training and validation order"


def test_verify_fold_chronology_catches_a_deliberately_broken_fold():
    """verify_fold_chronology() is what the main script actually
    calls before trusting a fold's metrics -- this proves it would
    catch a real violation, not just pass silently on good input.
    """
    months = pd.to_datetime(pd.date_range("2020-01-01", periods=20, freq="MS")).to_numpy()
    good_train_idx = np.arange(0, 10)
    good_val_idx = np.arange(10, 15)
    rme.verify_fold_chronology(good_train_idx, good_val_idx, months, fold_num=1)  # should not raise

    broken_val_idx = np.arange(5, 10)  # overlaps/precedes the training indices
    try:
        rme.verify_fold_chronology(good_train_idx, broken_val_idx, months, fold_num=1)
        assert False, "expected an AssertionError for overlapping train/val indices"
    except AssertionError as exc:
        assert "precedes" in str(exc) or "overlaps" in str(exc)


# ---------------------------------------------------------------------
# Across folds -- the literal "no index from a later fold appears
# before one from an earlier fold" requirement
# ---------------------------------------------------------------------

def test_no_index_from_a_later_fold_precedes_an_earlier_fold():
    train = _load_train()
    folds = rme.get_cv_folds(len(train))

    for i in range(len(folds) - 1):
        _, val_idx_current = folds[i]
        _, val_idx_next = folds[i + 1]
        assert val_idx_next.min() > val_idx_current.max(), (
            f"fold {i + 2}'s validation indices reach back into fold {i + 1}'s territory"
        )


def test_later_folds_train_on_a_superset_of_earlier_folds_data():
    """TimeSeriesSplit's expanding window: fold N's training set
    should contain every index fold N-1 ever saw (train or val) --
    confirms folds accumulate history forward, never reset or skip.
    """
    train = _load_train()
    folds = rme.get_cv_folds(len(train))

    for i in range(len(folds) - 1):
        train_idx_current, val_idx_current = folds[i]
        train_idx_next, _ = folds[i + 1]
        seen_so_far = set(train_idx_current) | set(val_idx_current)
        assert seen_so_far.issubset(set(train_idx_next))


def test_validation_months_never_precede_training_months():
    """Same check as the two above, but against the real calendar
    dates rather than positional indices -- ties the abstract index
    ordering back to something a reader can sanity-check by eye.
    """
    train = _load_train()
    months = train["month"].to_numpy()

    for fold_num, (train_idx, val_idx) in enumerate(rme.get_cv_folds(len(train)), start=1):
        assert months[train_idx].max() < months[val_idx].min(), (
            f"fold {fold_num}: a validation month is not strictly after every training month"
        )
