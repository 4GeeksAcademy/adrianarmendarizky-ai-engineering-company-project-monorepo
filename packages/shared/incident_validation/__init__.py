"""
packages/shared/incident_validation

The CSV validation rules from the incident-file-analyzer project
(CONTEXT-brasaland.md), extracted so they have exactly one home instead of
being duplicated between scripts/analyze.py and scripts/seed_incidents.py.

Both of those import this package directly instead of redefining any of
these rules themselves. If a rule ever changes, it changes here once.

This package only knows about the *analyzer's* CSV schema (location_id,
category codes like EQUIPMENT, statuses like OPEN/CLOSED/DISCARDED) — it
has no knowledge of the Incident Manager's model. Translating from one to
the other is seed_incidents.py's job, not this package's.
"""
import csv
import io

# ---------------------------------------------------------------------------
# Constants pulled directly from CONTEXT-brasaland.md — change here if the
# company ever adds a location or a category, nowhere else.
# ---------------------------------------------------------------------------

VALID_LOCATIONS = {f"COL-{n:02d}" for n in range(1, 11)} | {f"FLA-{n:02d}" for n in range(1, 5)}

# Order here is also the display order wherever this is printed.
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
# they're checked.
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
    """Parse CSV content already in memory (a string) into a list of row dicts."""
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


def load_records(csv_path):
    """Read a CSV file from disk and return a list of row dicts (raw, unvalidated)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return load_records_from_text(f.read())


def split_records(records):
    """
    Run every record through validate_record and split them into two lists:
    valid records and invalid records (as (row, failed_rules) pairs). Also
    returns a count per rule type.
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
