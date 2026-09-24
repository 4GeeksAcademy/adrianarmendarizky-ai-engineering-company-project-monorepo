"""
services/api/agent/tools.py -- Part 2 of 2 (external tools): typed
contracts and real HTTP calls into the incident manager and inventory
manager this monorepo already has. Neither function here ever invents or
simulates a response -- each either returns real data from the live
service or raises one of the specific exceptions below, which
nodes.py turns into an honest fallback message.

Both tools call the SAME running FastAPI app (services/api itself) over
HTTP rather than in-process, on purpose: the ticket lookup specifically
needs to demonstrate real backend-to-backend auth (a minted JWT, read
from config, never hardcoded), which an in-process call would skip
entirely. INTERNAL_API_BASE_URL defaults to http://localhost:8000 --
this is always correct (self-call, same container/host either way),
unlike QDRANT_URL, which needed a different value inside Docker.
"""

import os

import httpx
from pydantic import BaseModel

INTERNAL_API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "http://localhost:8000")

# Concrete, numeric timeouts (the ticket's own requirement) -- a hung
# incident/inventory service must never hang the graph.
TICKET_API_TIMEOUT_SECONDS = 5.0
INVENTORY_API_TIMEOUT_SECONDS = 5.0


# --- Ticket (incident manager) tool ----------------------------------


class TicketLookupResult(BaseModel):
    """Typed output contract -- mirrors incident_models.Incident's real
    fields exactly (services/api/incident_models.py); nothing here is
    invented or renamed for convenience."""

    id: int
    title: str
    status: str
    category: str
    origin: str
    branch: str
    created_at: str
    updated_at: str


class TicketNotFoundError(Exception):
    """The incident service responded normally: no ticket with that ID."""


class TicketServiceUnavailableError(Exception):
    """The call itself failed -- timeout, connection error, non-200/404,
    or no service-account credentials configured."""


def _mint_service_token() -> str:
    """Mints a real, validly-signed JWT for this one backend-to-backend
    call, reusing security.create_access_token() -- the exact same
    function every user login already goes through, not a second JWT
    implementation. AGENT_SERVICE_USER_ID (a real user id in your TinyDB
    users table) comes from the environment, never hardcoded -- see the
    setup instructions for how to set it."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # services/api
    from security import create_access_token  # noqa: E402

    user_id = os.environ.get("AGENT_SERVICE_USER_ID")
    if not user_id:
        raise TicketServiceUnavailableError(
            "AGENT_SERVICE_USER_ID is not set -- the ticket tool has no account to authenticate as."
        )
    return create_access_token(int(user_id))


def lookup_ticket(ticket_id: int) -> TicketLookupResult:
    """GET /api/incidents/{ticket_id} against the real, running incident
    manager. Read-only -- this function has no write counterpart and
    never will; a tool must never create, update, or delete a ticket."""
    token = _mint_service_token()
    try:
        response = httpx.get(
            f"{INTERNAL_API_BASE_URL}/api/incidents/{ticket_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TICKET_API_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise TicketServiceUnavailableError(
            f"incident service did not respond within {TICKET_API_TIMEOUT_SECONDS}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise TicketServiceUnavailableError(f"could not reach incident service: {exc}") from exc

    if response.status_code == 404:
        raise TicketNotFoundError(f"no ticket with id {ticket_id}")
    if response.status_code != 200:
        raise TicketServiceUnavailableError(f"incident service returned {response.status_code}")

    return TicketLookupResult(**response.json())


# --- Inventory (inventory manager) tool -- stretch goal ---------------


class InventoryMatch(BaseModel):
    """Typed output contract -- mirrors inventory_schemas.IngredientRead's
    real fields (services/api/inventory_schemas.py)."""

    id: int
    name: str
    sku: str
    current_stock: float


class InventoryServiceUnavailableError(Exception):
    """The call itself failed -- timeout, connection error, or non-200.
    Distinct from "the service answered but nothing matched" (see
    lookup_inventory's docstring) -- that's a normal empty result, not
    a failure, and the caller must be able to tell the two apart."""


def lookup_inventory(question: str) -> list[InventoryMatch]:
    """GET /inventory/products against the real, running inventory
    manager (no auth required -- this route is public, confirmed by
    reading routes/inventory.py directly), then matches the REAL
    product names against the question text -- rather than trying to
    parse a product name out of the question in isolation, which is
    the more fragile direction. An empty list is a legitimate,
    non-error result: the service answered, nothing in the real catalog
    matched what was asked. Read-only, same as lookup_ticket -- no
    write counterpart."""
    try:
        response = httpx.get(
            f"{INTERNAL_API_BASE_URL}/inventory/products",
            timeout=INVENTORY_API_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise InventoryServiceUnavailableError(
            f"inventory service did not respond within {INVENTORY_API_TIMEOUT_SECONDS}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise InventoryServiceUnavailableError(f"could not reach inventory service: {exc}") from exc

    if response.status_code != 200:
        raise InventoryServiceUnavailableError(f"inventory service returned {response.status_code}")

    products = response.json()
    question_lower = question.lower()
    matches = [p for p in products if p["name"].lower() in question_lower]
    return [InventoryMatch(**m) for m in matches]
