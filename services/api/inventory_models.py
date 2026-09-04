"""
inventory_models.py -- SQLModel ORM classes for the inventory feature.

Named to match the rest of the codebase's convention (user_models.py,
incident_models.py) instead of the generic "models.py" -- that also
means the existing models.py (Supplier's Pydantic models) never has
to be touched or renamed for this milestone.

These map directly to Supabase (Postgres) tables. Nothing here talks
to TinyDB -- users/auth/profiles/suppliers stay exactly where they
are.

table=True is what tells SQLModel "this class is also a database
table, not just a Pydantic model" -- that's the ORM part: each class
becomes a table, each instance becomes a row, each attribute becomes
a column.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Ingredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sku: str = Field(unique=True, index=True)
    unit: str
    category: str
    country: str
    # current_stock is intentionally NOT a column here. Per the business
    # rule in CONTEXT.md, it's always calculated from IngredientEntry /
    # IngredientExit rows -- never stored, never directly editable.
    # minimum_stock: added for the telemetry unit's stock_threshold_triggered
    # mandatory event (docs/telemetry/telemetry-plan.md). Optional with a
    # None default on purpose -- seed_inventory.py's existing Ingredient(...)
    # calls don't set it, and a required field here would break app startup.
    # No ingredient has one set yet except where seed_inventory.py opts in
    # for demo purposes.
    minimum_stock: Optional[float] = None


class IngredientEntry(SQLModel, table=True):
    """A delivery received from a supplier -- adds stock."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    quantity: float
    supplier_name: str
    location_id: int  # 1-14 -- not a FK, location data lives elsewhere
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_uuid: str  # references a TinyDB user's id -- no real FK possible across two databases
    # unit_cost: added for ingredient_price_variance_detected (telemetry
    # unit). Optional/None default for the same reason as minimum_stock
    # above -- existing seed rows and any future caller that omits it
    # must keep working.
    unit_cost: Optional[float] = None


class IngredientExit(SQLModel, table=True):
    """A consumption log or waste report -- removes stock."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    quantity: float
    reason: str  # "consumption" or "waste" -- enforced in inventory_schemas.py, not here
    location_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_uuid: str
    # waste_reason: sub-classification for stock_waste_registered, only
    # meaningful when reason="waste". Optional/None -- enforced to the
    # CONTEXT-specified enum in inventory_schemas.py, not here, matching
    # how `reason` itself is already handled.
    waste_reason: Optional[str] = None
    # unit_cost: added for the business performance pipeline's Waste Cost
    # per Location KPI (data/pipelines/PIPELINE_DESIGN.md, "Schema
    # prerequisite #1"). Unlike IngredientEntry.unit_cost above, this is
    # never supplied by the caller -- a waste report has no purchase price
    # of its own. routes/inventory.py's create_exit fills it in from the
    # ingredient's most recent IngredientEntry.unit_cost, the same
    # "look at prior entries" pattern already used there for
    # historical_avg_cost. Optional/None for the same reason as every
    # other field added this way: existing seed rows and any ingredient
    # with no cost history yet must keep working.
    #
    # NOTE: if you're setting up a fresh environment where `ingredientexit`
    # already exists from an earlier milestone, create_all() will NOT add
    # this column to it -- create_all() only creates missing tables, never
    # alters existing ones. Run this manually in Supabase's SQL Editor:
    #   ALTER TABLE ingredientexit ADD COLUMN unit_cost DOUBLE PRECISION;
    # Skipping this shows up as "Failed to fetch" on the frontend when
    # logging waste -- the real error (UndefinedColumn) is in the API
    # container logs, not the browser.
    unit_cost: Optional[float] = None