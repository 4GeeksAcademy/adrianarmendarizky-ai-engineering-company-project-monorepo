"""
analyze.py — Brasaland Incident Report Processor (Phase 1)

Reads a CSV of after-sales incident records, validates each row against the
rules in CONTEXT-brasaland.md, and prints a summary of the valid data plus a
breakdown of why any invalid rows were rejected.

Usage:
    python analyze.py incidents-brasaland.csv

Design note: every function below is a plain function that takes data in and
returns data out — none of them print anything or touch the CLI. That's on
purpose. In Phase 2 the API will need this exact same validation and
metrics logic, so keeping it separate from the "print stuff to the terminal"
code means we can import these functions later instead of copy-pasting them.
Only main() (at the bottom) deals with argv, printing, and the y/n prompt.
"""

import csv
import io
import sys

# ---------------------------------------------------------------------------
# Constants pulled directly from CONTEXT-brasaland.md — change here if the
# company ever adds a location or a category, nowhere else.
# ---------------------------------------------------------------------------

VALID_LOCATIONS = {f"COL-{n:02d}" for n in range(1, 11)} | {f"FLA-{n:02d}" for n in range(1, 5)}

# Order here is also the display order in the console/CSV output.
CATEGORY_ORDER = [
    "CUSTOMER_COMPLAINT",
    "EQUIPMENT",
    "SUPPLY",
    "FOOD_QUALITY",
    "STAFF",
]
VALID_CATEGORIES = set(CATEGORY_ORDER)

STATUS_ORDER = ["OPEN", "CLOSED", "DISCARDED"]
VALID_STATUSES = set(STATUS_ORDER)

# The 6 rules from the "Rules for Invalid Records" table, in the order
# they're checked. Keeping them as an ordered list (not just a dict) makes
# the console/CSV output print in a predictable, readable order.
INVALID_RULES = [
    "missing_location_id",
    "invalid_category",
    "empty_description",
    "missing_reporter_id",
    "closed_no_score",
    "score_out_of_range",
]

RULE_LABELS = {
    "missing_location_id": "Missing location_id",
    "invalid_category": "Invalid or missing category",
    "empty_description": "Empty description",
    "missing_reporter_id": "Missing reporter_id",
    "closed_no_score": "Closed case, no score",
    "score_out_of_range": "Satisfaction score out of range",
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_record(row):
    """
    Check one CSV row (a dict) against the 6 rules from CONTEXT.

    Returns a list of rule names that this row fails. An empty list means
    the row is valid. A row can fail more than one rule at once.
    """
    failed = []

    location_id = (row.get("location_id") or "").strip()
    if not location_id or location_id not in VALID_LOCATIONS:
        failed.append("missing_location_id")

    category = (row.get("category") or "").strip()
    if not category or category not in VALID_CATEGORIES:
        failed.append("invalid_category")

    description = (row.get("description") or "").strip()
    if len(description) < 5:
        failed.append("empty_description")

    reporter_id = (row.get("reporter_id") or "").strip()
    if not reporter_id:
        failed.append("missing_reporter_id")

    status = (row.get("status") or "").strip()
    raw_score = (row.get("satisfaction_score") or "").strip()

    if status == "CLOSED" and not raw_score:
        failed.append("closed_no_score")

    if raw_score:
        try:
            score = int(raw_score)
            if score < 1 or score > 5:
                failed.append("score_out_of_range")
        except ValueError:
            # Not even a number — that's also "out of range" for our purposes.
            failed.append("score_out_of_range")

    return failed


def parse_score(row):
    """Return the row's satisfaction_score as an int, or None if absent/unparseable."""
    raw = (row.get("satisfaction_score") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Loading + splitting the file
# ---------------------------------------------------------------------------

def load_records_from_text(csv_text):
    """
    Parse CSV content that's already in memory (a string) into a list of row
    dicts. This is the piece the API reuses directly — an uploaded file
    arrives as bytes/text, not as a path on disk, so this is the shared
    entry point both the script and the API call into.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


def load_records(csv_path):
    """Read a CSV file from disk and return a list of row dicts (raw, unvalidated)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return load_records_from_text(f.read())


def split_records(records):
    """
    Run every record through validate_record and split them into two lists:
    valid records and invalid records. Also returns a count per rule type,
    so we know *why* the invalid ones were rejected.
    """
    valid = []
    invalid = []
    rule_counts = {rule: 0 for rule in INVALID_RULES}

    for row in records:
        failed_rules = validate_record(row)
        if failed_rules:
            invalid.append((row, failed_rules))
            for rule in failed_rules:
                rule_counts[rule] += 1
        else:
            valid.append(row)

    return valid, invalid, rule_counts


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
    except FileNotFoundError:
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)

    total_records = len(records)
    valid, invalid, rule_counts = split_records(records)
    metrics = compute_metrics(valid)

    print_summary(csv_path, total_records, len(invalid), rule_counts, metrics)

    answer = input("Export results to CSV? [y / n]: ").strip().lower()
    if answer == "y":
        rows = build_export_rows(total_records, len(invalid), rule_counts, metrics)
        export_to_csv(rows, "results.csv")
        print("Saved to results.csv")


if __name__ == "__main__":
    main()
