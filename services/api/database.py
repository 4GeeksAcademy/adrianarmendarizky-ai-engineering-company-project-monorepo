"""
database.py -- database setup for the Brasaland API.

Two separate databases, on purpose:
- TinyDB (below) is unchanged and keeps handling users/auth/profiles/
  suppliers/incidents, exactly as before.
- SQLModel + Postgres (Supabase) is new, and is used ONLY for the
  inventory feature (Ingredient, IngredientEntry, IngredientExit).
Nothing about the TinyDB half changes as part of this milestone.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine
from tinydb import TinyDB

# Defensive: main.py already calls load_dotenv() before anything else is
# imported, but scripts/ sometimes import this module directly without
# going through main.py first. Calling load_dotenv() again here is
# harmless (it just re-reads .env) and makes this module safe to import
# on its own.
load_dotenv()

# ---------------------------------------------------------------------------
# TinyDB -- unchanged from the supplier-directory / auth milestones
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "db.json"

db = TinyDB(DB_PATH)

# TinyDB organizes data into "tables" (similar to a table in SQL). All
# supplier records live in this one table.
suppliers_table = db.table("suppliers")

# AUTH-01: User and Profile stay in TinyDB permanently -- even after
# Supabase/Postgres is introduced below, these two tables are never
# migrated. The inventory module only ever stores a user's id as
# user_uuid, never a copy of the row.
users_table = db.table("users")
profiles_table = db.table("profiles")

# AUTH-03: password reset tokens. Only a hash of each token is ever
# stored here -- the raw token exists only in the email it's sent in,
# same principle as never storing a plaintext password.
password_resets_table = db.table("password_resets")

# Centralized Incident Manager. Each document also carries an internal
# "source_ref" key (the historical CSV's incident_id, when the record
# came from scripts/seed_incidents.py) used only for that script's own
# duplicate-detection on re-runs -- it's never part of the Incident
# Pydantic model, so it never appears in an API response.
incidents_table = db.table("incidents")

# ---------------------------------------------------------------------------
# Supabase (Postgres) via SQLModel -- new, inventory only
# ---------------------------------------------------------------------------

# Set this in .env once you've created your Supabase project (Connect ->
# Direct -> Transaction pooler -> URI). Never hardcode it here.
DATABASE_URL = os.getenv("DATABASE_URL")

# echo=False keeps the terminal quiet; set to True temporarily if you
# ever need to see the raw SQL SQLModel is generating.
engine = create_engine(DATABASE_URL, echo=False) if DATABASE_URL else None


def init_inventory_db() -> None:
    """Create the inventory tables in Supabase if they don't exist yet.

    Called once on startup, from main.py's lifespan. Deliberately does
    NOT raise when DATABASE_URL is unset -- it just skips itself. Two
    reasons: (1) it lets the rest of the app boot normally before
    you've set up Supabase, and (2) tests/conftest.py spins up the full
    app -- including this lifespan step -- for every test, and never
    sets DATABASE_URL, so raising here would break the entire existing
    test suite, not just inventory tests.

    get_db() below is where a *missing* connection should actually
    fail loudly -- that only happens if someone hits a real /inventory
    endpoint without DATABASE_URL configured.
    """
    if engine is None:
        print("DATABASE_URL not set -- skipping inventory table setup.")
        return

    # Imported here, not at the top of the file, so this module can
    # still be imported by code that only needs TinyDB, without also
    # requiring inventory_models.py's SQLModel table classes to exist.
    import inventory_models  # noqa: F401  (import registers the tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)


def get_db():
    """Yields one Supabase session per request. Use with Depends(get_db).

    Unlike init_inventory_db(), THIS raises when DATABASE_URL is unset --
    at this point someone is actually trying to read/write inventory
    data, so a clear error is the right behavior, not a silent skip.
    """
    if engine is None:
        raise RuntimeError(
            "DATABASE_URL is not set. Add your Supabase connection "
            "string to .env before using any /inventory endpoint."
        )
    with Session(engine) as session:
        yield session
