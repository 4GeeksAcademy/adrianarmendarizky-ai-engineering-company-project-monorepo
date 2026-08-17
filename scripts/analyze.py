"""
analyze.py — Brasaland Incident Report Processor

Reads a CSV of after-sales incident records, validates each row against the
rules in CONTEXT-brasaland.md, and prints a summary of the valid data plus a
breakdown of why any invalid rows were rejected.

Usage:
    python analyze.py incidents-brasaland.csv

The validation rules themselves (what counts as a valid row, the category
and location lists) now live in packages/shared/incident_validation — this
script and scripts/seed_incidents.py both import from there instead of each
defining their own copy. Everything below this point is specific to *this*
script: computing the analyzer's own metrics and printing them.
"""

import csv
import sys
from pathlib import Path

# packages/shared/ lives two levels up from this file: scripts/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_DIR = REPO_ROOT / "packages" / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from incident_validation import (  # noqa: E402
    CATEGORY_ORDER,
    INVALID_RULES,
    RULE_LABELS,
    STATUS_ORDER,
    load_records,
    load_records_from_text,
    parse_score,
    split_records,
)


# ---------------------------------------------------------------------------
# Metrics (computed on valid records only)
# ---------------------------------------------------------------------------

def compute_metrics(valid_records):
    """
    Compute the 4 metrics required for valid records:
      - total processed (valid count)
      - breakdown by category
      - breakdown by status
      - average satisfaction index for closed cases with a score
    Returns everything as a dict of plain data (no printing here).
    """
    total_valid = len(valid_records)

    category_counts = {cat: 0 for cat in CATEGORY_ORDER}
    status_counts = {status: 0 for status in STATUS_ORDER}
    score_counts = {n: 0 for n in range(1, 6)}

    for row in valid_records:
        category_counts[row["category"].strip()] += 1
        status_counts[row["status"].strip()] += 1

        score = parse_score(row)
        if row["status"].strip() == "CLOSED" and score is not None:
            score_counts[score] += 1

    closed_total = status_counts["CLOSED"]
    scored_count = sum(score_counts.values())
    score_sum = sum(score * count for score, count in score_counts.items())
    average_score = round(score_sum / scored_count, 2) if scored_count else 0.0

    return {
        "total_valid": total_valid,
        "category_counts": category_counts,
        "status_counts": status_counts,
        "closed_total": closed_total,
        "scored_count": scored_count,
        "score_counts": score_counts,
        "average_score": average_score,
    }


def pct(count, total):
    """Percentage of `count` out of `total`, 1 decimal place. 0 if total is 0."""
    return round((count / total) * 100, 1) if total else 0.0


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

SCORE_LABELS = {
    1: "Very dissatisfied",
    2: "Dissatisfied",
    3: "Neutral",
    4: "Satisfied",
    5: "Very satisfied",
}


def print_summary(csv_path, total_records, invalid_count, rule_counts, metrics):
    total_valid = metrics["total_valid"]

    print("=" * 60)
    print("  BRASALAND — INCIDENT REPORT ANALYSIS")
    print(f"  Source file: {csv_path}")
    print("=" * 60)
    print()
    print(f"TOTAL RECORDS IN FILE .......... {total_records}")
    print(f"  |- Valid records ................ {total_valid}")
    print(f"  '- Invalid / incomplete .......... {invalid_count}")
    print()

    print("INVALID RECORDS BREAKDOWN")
    nonzero_rules = [r for r in INVALID_RULES if rule_counts[r] > 0]
    for i, rule in enumerate(nonzero_rules):
        branch = "'-" if i == len(nonzero_rules) - 1 else "|-"
        print(f"  {branch} {RULE_LABELS[rule]} ... {rule_counts[rule]}")
    if not nonzero_rules:
        print("  (none)")
    print()

    print("BREAKDOWN BY CATEGORY (valid records)")
    cats = list(metrics["category_counts"].items())
    for i, (cat, count) in enumerate(cats):
        branch = "'-" if i == len(cats) - 1 else "|-"
        print(f"  {branch} {cat} ... {count}  ({pct(count, total_valid)}%)")
    print()

    print("BREAKDOWN BY STATUS (valid records)")
    statuses = list(metrics["status_counts"].items())
    for i, (status, count) in enumerate(statuses):
        branch = "'-" if i == len(statuses) - 1 else "|-"
        print(f"  {branch} {status} ... {count}  ({pct(count, total_valid)}%)")
    print()

    print("SATISFACTION INDEX (closed cases)")
    print(f"  Scored cases: {metrics['scored_count']} of {metrics['closed_total']}")
    print(f"  Average score: {metrics['average_score']:.2f} / 5.00")
    scores = list(metrics["score_counts"].items())
    for i, (score, count) in enumerate(scores):
        branch = "'-" if i == len(scores) - 1 else "|-"
        print(f"  {branch} Score {score} ({SCORE_LABELS[score]}) ... {count}")
    print()
    print("=" * 60)


# ---------------------------------------------------------------------------
# CSV export — one row per metric, columns: metric, value, percentage
# ---------------------------------------------------------------------------

def build_export_rows(total_records, invalid_count, rule_counts, metrics):
    rows = [
        {"metric": "total_records", "value": total_records, "percentage": ""},
        {"metric": "valid_records", "value": metrics["total_valid"], "percentage": ""},
        {"metric": "invalid_records", "value": invalid_count, "percentage": ""},
    ]

    for rule in INVALID_RULES:
        rows.append({"metric": f"invalid_{rule}", "value": rule_counts[rule], "percentage": ""})

    for cat, count in metrics["category_counts"].items():
        rows.append({
            "metric": f"category_{cat}",
            "value": count,
            "percentage": pct(count, metrics["total_valid"]),
        })

    for status, count in metrics["status_counts"].items():
        rows.append({
            "metric": f"status_{status}",
            "value": count,
            "percentage": pct(count, metrics["total_valid"]),
        })

    rows.append({"metric": "satisfaction_scored_cases", "value": metrics["scored_count"], "percentage": ""})
    rows.append({"metric": "satisfaction_average", "value": metrics["average_score"], "percentage": ""})
    for score, count in metrics["score_counts"].items():
        rows.append({"metric": f"satisfaction_score_{score}", "value": count, "percentage": ""})

    return rows


def export_to_csv(rows, output_path="results.csv"):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value", "percentage"])
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze.py <path-to-csv>")
        sys.exit(1)

    csv_path = sys.argv[1]

    try:
        records = load_records(csv_path)
        total_records = len(records)
        valid, invalid, rule_counts = split_records(records)
        metrics = compute_metrics(valid)

        print_summary(csv_path, total_records, len(invalid), rule_counts, metrics)

        answer = input("Export results to CSV? [y / n]: ").strip().lower()
        if answer == "y":
            rows = build_export_rows(total_records, len(invalid), rule_counts, metrics)
            export_to_csv(rows, "results.csv")
            print("Saved to results.csv")
    except FileNotFoundError:
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)
    except Exception as exc:
        print(f"Error: analysis failed unexpectedly: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
