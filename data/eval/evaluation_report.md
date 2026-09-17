# Sales Forecasting Model — Technical Evaluation Report

Evaluates the Random Forest model from `scripts/sales_forecast_train.py` using
5-fold time-aware cross-validation and a learning curve over the training
period only (2017-01 to 2023-12, 84 months after feature engineering — the
2024-2025 held-out test set is untouched by this report). Full numbers behind
every figure below are in `data/eval/cv_metrics.json`; the learning curve
image is `data/eval/learning_curve.png`.

## 1. Diagnosis: overfitting (moderate, not severe)

| | Train MAE | Val MAE | Gap |
|---|---|---|---|
| Mean ± std across 5 folds | $11,587 ± $1,511 | $37,326 ± $13,711 | $25,739 (69% of val error) |

Two independent pieces of evidence point the same way:

- **Cross-validation gap.** Training error is low and tight (std is only 13%
  of the mean). Validation error is more than 3x higher and much more
  variable. A wide, persistent train/validation gap like this is the
  textbook overfitting signature — not underfitting (training error would
  have to be high too) and not a good fit (train and val would have to be
  close).
- **Learning curve** (`data/eval/learning_curve.png`). Training error stays
  essentially flat (~$10K-15K) no matter how much history the model sees.
  Validation error (measured against a fixed, most-recent 14-month window)
  drops sharply as training data grows — from ~$199K with only 12 months of
  history to ~$51K-62K with the full 70 months available — but never
  converges with training error, even at the largest training size tested.

(Note on how the learning curve was built: sklearn's `learning_curve()` with
a `TimeSeriesSplit` cv caps the training size at the *smallest* fold's
training set — 14 months here — which produced a misleadingly narrow,
uninformative curve. Instead, `generate_learning_curve()` fixes the last 14
months of the training period as a single validation window and expands the
training window backward from 2017-01 in steps of 12 months, up to the full
70 months available before that window.)

## 2. Stability across folds (how consistent is performance?)

Not very. Validation MAE ranges from $23,214 (fold 2) to $62,886 (fold 5) —
a standard deviation that's 37% of the mean validation error:

| Fold | Train months | Val MAE | Val RMSE |
|---|---|---|---|
| 1 | 14 | $32,062 | $46,818 |
| 2 | 28 | $23,214 | $30,729 |
| 3 | 42 | $38,739 | $49,163 |
| 4 | 56 | $29,728 | $37,405 |
| 5 | 70 | $62,886 | $73,873 |

Fold 5 — validating on the most recent training months (2022-2023) — is the
clear outlier. That window includes an especially large December spike
relative to the growth trend the earlier folds were trained on, which the
model underweights. A model that had genuinely learned the seasonal/growth
pattern (rather than partly memorizing the months it trained on) would be
expected to generalize with more consistent error across different
validation windows than this.

## 3. Corrective action: regularize first, more data second

Tested lowering `max_depth` from 6 to 3 and raising `min_samples_leaf` from 2
to 6 (the current values are set in `scripts/sales_forecast_train.py`,
`train_model()`, lines 173-181) using the same 5-fold CV:

| Configuration | Train MAE | Val MAE | Gap (% of val) |
|---|---|---|---|
| Current (depth=6, leaf=2) | $11,587 | $37,326 | 69.0% |
| Regularized (depth=3, leaf=6) | $24,861 | $37,006 | 32.8% |

Validation error is essentially unchanged ($37,326 → $37,006) while the gap
more than halves, because training error *rises* — the trees can no longer
memorize each fold's small training window almost exactly. Validation
performance holding steady while the gap narrows is the specific signature
of a capacity fix working, not a coincidence of one run; it's why this is
the recommended action rather than a generic "add regularization."

More data would likely help too — the learning curve hadn't plateaued by 70
months — but that's a lever tied to the calendar (waiting for future months
to accumulate), not something actionable today. Regularizing the 84 months
already available is the fix that can be applied now, and it's backed by
the table above rather than being a default guess.

**Recommendation:** update `train_model()` to `max_depth=3,
min_samples_leaf=6`, then re-run `scripts/sales_forecast_train.py` to
confirm the held-out 2024-2025 test metrics hold up. Not done as part of
this report — this ticket is about diagnosing the existing shipped model,
not shipping a new one.

## 4. Metric choice: MAE vs. RMSE

Both are calculated for every fold (table in section 2; full detail in
`cv_metrics.json`). RMSE is consistently larger than MAE — e.g., mean
validation RMSE is $47,598 vs. mean validation MAE of $37,326 — because
squaring errors before averaging weighs large misses (like fold 5's
December-driven miss) much more heavily than typical ones.

**On the business justification:** I re-read `context-time-series.md` in
full, twice, looking specifically for which direction of error — over- or
under-forecasting — costs Brasaland more, and it does not say. What the
document does establish (section 1) is that Felipe's ingredient purchasing
and Lucía's meat-volume procurement both key off this forecast, and
Brasaland's product is perishable meat. Reasoning from that alone:
underforecasting risks stockouts during a real demand spike (lost sales,
turned-away guests); overforecasting risks over-ordering meat that spoils.
Neither is clearly worse from what the document actually says — but a large,
infrequent miss (like fold 5's) is the scenario most likely to push either
failure mode to a level that actually disrupts a location's ordering, and
that's exactly the kind of error RMSE is more sensitive to.

**On that basis, this report treats RMSE as the primary metric**, with MAE
reported alongside as the more interpretable, typical-month figure for
Felipe and Mariana. This is my own reasoning from the document, not
something it states directly — worth confirming with your tech lead, since
the ticket implies this justification should come straight from the context
file, and in this case the file doesn't contain it.

## Files produced

- `scripts/regression_model_eval.py` — cross-validation, learning curve, and
  diagnosis logic
- `data/eval/learning_curve.png`
- `data/eval/cv_metrics.json` — full per-fold numbers behind every table above
- `tests/pipelines/test_temporal_cv_order.py` — validates fold chronology
