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
    minimum_stock: Optional[float] = None


class IngredientRead(BaseModel):
    id: int
    name: str
    sku: str
    unit: str
    category: str
    country: str
    current_stock: float  # computed by the router -- never trust a client-sent value
    minimum_stock: Optional[float] = None


class IngredientEntryCreate(BaseModel):
    ingredient_id: int
    quantity: float
    supplier_name: str
    location_id: int
    unit_cost: Optional[float] = None


class IngredientEntryRead(BaseModel):
    id: int
    ingredient_id: int
    quantity: float
    supplier_name: str
    location_id: int
    created_at: datetime
    user_uuid: str
    unit_cost: Optional[float] = None
    # historical_avg_cost: computed by the router from prior entries for
    # this ingredient+supplier (never including the row just created).
    # None when there's no prior cost data to compare against. Telemetry
    # only -- not persisted, not a column on IngredientEntry.
    historical_avg_cost: Optional[float] = None
    # Denormalized from the parent Ingredient purely so the frontend's
    # telemetry call doesn't need a second lookup to fill in an event's
    # product_category/unit properties.
    product_category: str
    unit: str


class IngredientExitCreate(BaseModel):
    ingredient_id: int
    quantity: float
    # Literal here means Pydantic rejects anything other than these two
    # strings automatically (422), before your route code even runs --
    # that's what enforces the "reason must be consumption or waste" rule.
    reason: Literal["consumption", "waste"]
    location_id: int
    # Same Literal enforcement idea as `reason` -- only meaningful when
    # reason="waste", but not cross-validated against `reason` here (the
    # frontend only shows this field once "waste" is selected).
    waste_reason: Optional[Literal["expired", "kitchen_error", "theft_suspected"]] = None


class IngredientExitRead(BaseModel):
    id: int
    ingredient_id: int
    quantity: float
    reason: str
    location_id: int
    created_at: datetime
    user_uuid: str
    waste_reason: Optional[str] = None
    product_category: str
    unit: str
    # current_stock/minimum_stock: both post-write, so the frontend can
    # decide whether to fire stock_threshold_triggered without a second
    # request. minimum_stock is None whenever the ingredient doesn't
    # have one configured -- see inventory_models.py.
    current_stock: float
    minimum_stock: Optional[float] = None
    # unit_cost: computed by the router from the ingredient's most recent
    # purchase price (see routes/inventory.py's create_exit) -- never
    # persisted on IngredientExitCreate, same "telemetry only" treatment
    # IngredientEntryRead.historical_avg_cost gets above.
    unit_cost: Optional[float] = None


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
