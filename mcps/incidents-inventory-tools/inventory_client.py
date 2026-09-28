"""
mcps/incidents-inventory-tools/inventory_client.py -- the ONLY place
this MCP server talks to the real Inventory Manager. GET only -- there
is no function here that could write, on purpose: the read-only
guarantee this server makes for inventory holds at this layer too, not
just in server.py's tool definitions.

No auth token minted here: GET /inventory/products on the real
Inventory Manager doesn't require one (confirmed by reading
services/api/routes/inventory.py directly -- only the write routes
there declare get_current_user).
"""

import os

import httpx
from pydantic import BaseModel

INTERNAL_API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "http://localhost:8000")
TIMEOUT_SECONDS = 5.0


class InventoryItem(BaseModel):
    """Mirrors inventory_schemas.IngredientRead's real fields
    (services/api/inventory_schemas.py)."""

    id: int
    name: str
    sku: str
    unit: str
    category: str
    country: str
    current_stock: float
    minimum_stock: float | None = None


class InventoryServiceUnavailableError(Exception):
    pass


def query_products(name_contains: str | None = None) -> list[InventoryItem]:
    """GET /inventory/products, optionally filtered to items whose name
    contains `name_contains` (case-insensitive). Filtering happens here,
    client-side, against the real catalog -- the Inventory Manager's own
    /products route has no server-side name filter."""
    try:
        response = httpx.get(
            f"{INTERNAL_API_BASE_URL}/inventory/products", timeout=TIMEOUT_SECONDS
        )
    except httpx.TimeoutException as exc:
        raise InventoryServiceUnavailableError(
            f"inventory service did not respond within {TIMEOUT_SECONDS}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise InventoryServiceUnavailableError(f"could not reach inventory service: {exc}") from exc

    if response.status_code != 200:
        raise InventoryServiceUnavailableError(f"inventory service returned {response.status_code}")

    items = [InventoryItem(**item) for item in response.json()]
    if name_contains:
        needle = name_contains.lower()
        items = [item for item in items if needle in item.name.lower()]
    return items
