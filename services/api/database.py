"""
database.py -- TinyDB setup for the Brasaland Supplier Directory API.

TinyDB stores everything in a single JSON file on disk, so there's no
separate database server to install or run -- a good fit for a
lightweight tool like this one, per the tech lead's note in the brief.

This module creates one shared connection (and one shared "suppliers"
table) that the rest of the app imports and reuses, so every part of
the API is reading and writing the same data.
"""

from pathlib import Path

from tinydb import TinyDB

# The JSON file TinyDB reads from / writes to. Using a path relative to
# this file (instead of a plain "db.json") means the database always
# lands in the same place, no matter what folder you run uvicorn from.
DB_PATH = Path(__file__).parent / "db.json"

db = TinyDB(DB_PATH)

# TinyDB organizes data into "tables" (similar to a table in SQL). All
# supplier records live in this one table.
suppliers_table = db.table("suppliers")

# AUTH-01: User and Profile stay in TinyDB permanently -- even after
# Supabase/Postgres is introduced elsewhere in the project, these two
# tables are never migrated. Other Postgres-backed modules will only
# ever store this User's id as user_uuid, never a copy of the row.
users_table = db.table("users")
profiles_table = db.table("profiles")