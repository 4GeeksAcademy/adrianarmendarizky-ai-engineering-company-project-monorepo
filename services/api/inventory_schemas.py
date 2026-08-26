"""
inventory_schemas.py -- Pydantic request/response schemas for inventory.

Kept as a separate set of classes from inventory_models.py on purpose
(per the brief): the ORM classes describe the database tables, these
classes describe what the API actually accepts and returns. They
overlap in fields but are not the same classes -- current_stock is
the clearest example, since it exists here but is not a column in
inventory_models.py at all.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class IngredientCreate(BaseModel):
    name: str
    sku: str
    unit: str
    category: str
    country: str


class IngredientRead(BaseModel):
    id: int
    name: str
    sku: str
    unit: str
    category: str
    country: str
    current_stock: float  # computed by the router -- never trust a client-sent value


class IngredientEntryCreate(BaseModel):
    ingredient_id: int
    quantity: float
    supplier_name: str
    location_id: int


class IngredientEntryRead(BaseModel):
    id: int
    ingredient_id: int
    quantity: float
    supplier_name: str
    location_id: int
    created_at: datetime
    user_uuid: str


class IngredientExitCreate(BaseModel):
    ingredient_id: int
    quantity: float
    # Literal here means Pydantic rejects anything other than these two
    # strings automatically (422), before your route code even runs --
    # that's what enforces the "reason must be consumption or waste" rule.
    reason: Literal["consumption", "waste"]
    location_id: int


class IngredientExitRead(BaseModel):
    id: int
    ingredient_id: int
    quantity: float
    reason: str
    location_id: int
    created_at: datetime
    user_uuid: str


class InventoryOrderRead(BaseModel):
    """One row of the combined GET /inventory/orders feed.

    type distinguishes an inbound delivery from an outbound exit.
    supplier_name is only ever set on inbound rows; reason is only ever
    set on outbound rows.
    """

    type: Literal["inbound", "outbound"]
    id: int
    ingredient_id: int
    ingredient_name: str
    ingredient_sku: str
    quantity: float
    location_id: int
    created_at: datetime
    user_uuid: str
    supplier_name: Optional[str] = None
    reason: Optional[str] = None
