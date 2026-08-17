"""
scripts/seed_incidents.py

Loads the historical incidents-brasaland.csv (from the incident-file-analyzer
project) into the centralized Incident Manager's database, applying the
CSV -> model transformations from CONTEXT-brasaland.en (centralized).md.

Usage:
    python seed_incidents.py [path-to-csv]

If no path is given, this defaults to incidents-brasaland.csv sitting in
this same scripts/ folder (where the analyzer project already left it).

Reuses two things instead of redefining them:
  - CSV validation (what counts as a valid row at all) from
    packages/shared/incident_validation -- the same rules analyze.py uses.
  - The Incident Manager's own database connection and Pydantic model
    from services/api, so a seeded record is validated exactly the same
    way a record created through the live API would be.

Idempotent: safe to run more than once. Each transformed record's CSV
incident_id is stored internally (as "source_ref", never exposed by the
API -- see database.py) and checked before inserting, so a second run
reports everything as "already in database" and inserts nothing new.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_DIR = REPO_ROOT / "packages" / "shared"
API_DIR = REPO_ROOT / "services" / "api"
for path in (SHARED_DIR, API_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pydantic import ValidationError  # noqa: E402

from incident_validation import load_records, split_records  # noqa: E402
from database import incidents_table  # noqa: E402
from incident_models import IncidentSeedRecord  # noqa: E402

DEFAULT_CSV_PATH = Path(__file__).parent / "incidents-brasaland.csv"

# ---------------------------------------------------------------------------
# CSV -> model transformations, copied verbatim from
# CONTEXT-brasaland.en (centralized).md. If the company adds a location,
# category, or status, update the tables here -- nowhere else.
# ---------------------------------------------------------------------------

STATUS_MAP = {
    "OPEN": "open",
    "CLOSED": "resolved",
    "DISCARDED": "discarded",
}

CATEGORY_MAP = {
    "CUSTOMER_COMPLAINT": "customer_complaint",
    "EQUIPMENT": "equipment_failure",
    "SUPPLY": "supply_issue",
    "FOOD_QUALITY": "customer_complaint",
    "STAFF": "staff_issue",
}

# location_id -> branch. Anything missing or not in this table falls back
# to "central", per CONTEXT.
BRANCH_MAP = {
    "COL-01": "medellin_centro",
    "COL-02": "medellin_laureles",
    "COL-03": "medellin_envigado",
    "COL-04": "medellin_bello",
    "COL-05": "medellin_itagui",
    "COL-06": "bogota_chapinero",
    "COL-07": "bogota_usaquen",
    "COL-08": "cali_granada",
    "COL-09": "barranquilla_norte",
    "COL-10": "central",
    "FLA-01": "miami_doral",
    "FLA-02": "miami_hialeah",
    "FLA-03": "miami_kendall",
    "FLA-04": "orlando_international",
}


def transform(row):
    """
    Turn one already-valid analyzer CSV row into a dict matching
    IncidentSeedRecord. Returns (record_dict, source_ref) on success.
    Returns (None, reason) if the row must be discarded at this step --
    `reason` is a short string explaining why, for the console report.
    """
    title = row["description"].strip()[:120].strip()
    if not title:
        return None, "empty title after transformation"

    try:
        created_at = datetime.strptime(row["date"].strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None, f"unparseable date: {row.get('date')!r}"

    status = STATUS_MAP.get(row["status"].strip())
    if status is None:
        return None, f"unmapped status: {row['status']!r}"

    category = CATEGORY_MAP.get(row["category"].strip())
    if category is None:
        return None, f"unmapped category: {row['category']!r}"

    branch = BRANCH_MAP.get(row["location_id"].strip(), "central")

    record = {
        "title": title,
        "description": row["description"].strip(),
        "category": category,
        "origin": "customer",
        "branch": branch,
        "status": status,
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
    }

    source_ref = (row.get("incident_id") or row.get("ticket_id") or "").strip() or None
    return record, source_ref


def seed(csv_path):
    records = load_records(csv_path)
    total = len(records)
    valid, invalid, rule_counts = split_records(records)

    # Idempotency check: prefer the CSV's own incident_id (stored
    # internally as source_ref). Rows from a source without one fall back
    # to matching on title + created_at, per CONTEXT.
    existing_docs = incidents_table.all()
    existing_refs = {doc["source_ref"] for doc in existing_docs if doc.get("source_ref")}
    existing_title_created = {(doc["title"], doc["created_at"]) for doc in existing_docs}

    inserted = 0
    skipped_duplicate = 0
    skipped_transform = []

    for row in valid:
        record, source_ref = transform(row)
        if record is None:
            skipped_transform.append((row.get("incident_id", "?"), source_ref))
            continue

        try:
            IncidentSeedRecord(**record)
        except ValidationError as exc:
            skipped_transform.append(
                (row.get("incident_id", "?"), f"failed model validation: {exc.errors()[0]['msg']}")
            )
            continue

        is_duplicate = (
            source_ref in existing_refs
            if source_ref is not None
            else (record["title"], record["created_at"]) in existing_title_created
        )
        if is_duplicate:
            skipped_duplicate += 1
            continue

        doc = dict(record)
        if source_ref is not None:
            doc["source_ref"] = source_ref
        incidents_table.insert(doc)

        if source_ref is not None:
            existing_refs.add(source_ref)
        existing_title_created.add((record["title"], record["created_at"]))
        inserted += 1

    # --- console report ---
    print("=" * 60)
    print("  BRASALAND — HISTORICAL INCIDENT SEED")
    print(f"  Source file: {csv_path}")
    print("=" * 60)
    print()
    print(f"TOTAL ROWS IN FILE ............. {total}")
    print(f"  |- Invalid (analyzer rules) ..... {len(invalid)}")
    print(f"  |- Skipped at transform step .... {len(skipped_transform)}")
    print(f"  |- Already in database .......... {skipped_duplicate}")
    print(f"  '- Newly inserted ................ {inserted}")
    print()

    if invalid:
        print("INVALID ROWS (analyzer validation rules) — not inserted:")
        for row, failed_rules in invalid:
            ref = row.get("incident_id", "?")
            print(f"  - {ref}: {', '.join(failed_rules)}")
        print()

    if skipped_transform:
        print("ROWS SKIPPED AT THE TRANSFORM STEP — not inserted:")
        for ref, reason in skipped_transform:
            print(f"  - {ref}: {reason}")
        print()

    print("=" * 60)


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV_PATH
    if not csv_path.exists():
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)
    seed(str(csv_path))


if __name__ == "__main__":
    main()
