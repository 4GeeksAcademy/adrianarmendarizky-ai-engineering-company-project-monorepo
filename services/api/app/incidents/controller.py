"""
incidents/controller.py

Bridges the FastAPI layer to the exact same validation and analysis logic
used by scripts/analyze.py. Nothing here re-implements a rule.

The CSV validation rules (what counts as a valid row) come from
packages/shared/incident_validation, the same place scripts/seed_incidents.py
gets them from. The metrics/export formatting specific to this analyzer
feature (compute_metrics, build_export_rows, etc.) still comes from
scripts/analyze.py, since that part isn't shared with anything else.
"""
import sys
from pathlib import Path

# From this file: incidents/ -> app/ -> api/ -> services/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SHARED_DIR = REPO_ROOT / "packages" / "shared"
for path in (SCRIPTS_DIR, SHARED_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import analyze  # noqa: E402 (imports must come after the sys.path changes above)
from incident_validation import (  # noqa: E402
    INVALID_RULES,
    RULE_LABELS,
    load_records_from_text,
    split_records,
)


class EmptyFileError(Exception):
    """Raised when the uploaded file has no content."""


class InvalidCsvError(Exception):
    """Raised when the uploaded file can't be read as CSV data."""


# In-memory cache of the most recent analysis, so GET /results/export can
# hand back the same numbers the user just saw on screen. There's no
# database in this project yet, so a module-level variable is the same
# "keep it in memory" approach used for the to-do list in the voice
# command API project — it resets if the server restarts, which is fine
# for this use case.
_last_analysis = {"rows": None, "filename": None}


def run_analysis(filename: str, file_bytes: bytes) -> dict:
    """
    Run the full pipeline (parse -> validate -> compute metrics) on an
    uploaded file's raw bytes, cache the export rows for later, and return
    a JSON-ready dict of the summary.
    """
    if not file_bytes.strip():
        raise EmptyFileError("The uploaded file is empty.")

    try:
        csv_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidCsvError("The file isn't valid UTF-8 text.")

    records = load_records_from_text(csv_text)
    if not records:
        raise InvalidCsvError("No data rows found in the file.")

    total_records = len(records)
    valid, invalid, rule_counts = split_records(records)
    metrics = analyze.compute_metrics(valid)

    result = {
        "source_filename": filename,
        "total_records": total_records,
        "valid_records": metrics["total_valid"],
        "invalid_records": len(invalid),
        "invalid_breakdown": [
            {
                "rule": rule,
                "label": RULE_LABELS[rule],
                "count": rule_counts[rule],
            }
            for rule in INVALID_RULES
        ],
        "category_breakdown": [
            {
                "category": cat,
                "count": count,
                "percentage": analyze.pct(count, metrics["total_valid"]),
            }
            for cat, count in metrics["category_counts"].items()
        ],
        "status_breakdown": [
            {
                "status": status,
                "count": count,
                "percentage": analyze.pct(count, metrics["total_valid"]),
            }
            for status, count in metrics["status_counts"].items()
        ],
        "satisfaction": {
            "closed_total": metrics["closed_total"],
            "scored_count": metrics["scored_count"],
            "average_score": metrics["average_score"],
            "distribution": [
                {
                    "score": score,
                    "label": analyze.SCORE_LABELS[score],
                    "count": count,
                }
                for score, count in metrics["score_counts"].items()
            ],
        },
    }

    _last_analysis["rows"] = analyze.build_export_rows(
        total_records, len(invalid), rule_counts, metrics
    )
    _last_analysis["filename"] = filename

    return result


def get_last_export_rows():
    """Return the cached export rows from the last analysis, or None if none has run yet."""
    return _last_analysis["rows"]
