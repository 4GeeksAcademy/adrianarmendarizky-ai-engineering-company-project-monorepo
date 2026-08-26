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


class IngredientEntry(SQLModel, table=True):
    """A delivery received from a supplier -- adds stock."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    quantity: float
    supplier_name: str
    location_id: int  # 1-14 -- not a FK, location data lives elsewhere
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_uuid: str  # references a TinyDB user's id -- no real FK possible across two databases


class IngredientExit(SQLModel, table=True):
    """A consumption log or waste report -- removes stock."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id")
    quantity: float
    reason: str  # "consumption" or "waste" -- enforced in inventory_schemas.py, not here
    location_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_uuid: str
