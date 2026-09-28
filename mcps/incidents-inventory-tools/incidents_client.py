"""
mcps/incidents-inventory-tools/incidents_client.py -- the ONLY place
this MCP server talks to the real Incidents Manager (services/api).
Real HTTP, real JWT, explicit timeouts -- same pattern as
services/api/agent/tools.py's ticket tool, reused rather than
reinvented, even though this server is a separate package: it mints a
JWT with security.create_access_token() (services/api/security.py) so
this call is authenticated the same way every other backend-to-backend
call in this monorepo already is.

This module is intentionally thin: it has exactly one function per real
endpoint this server needs, each named after what it does, not a
generic "call the incidents API" wrapper. Status changes go through
update_ticket_status() -> PATCH /api/incidents/{id}/status specifically
-- never a generic PATCH on the incident resource, per the ticket's own
requirement.
"""

import os
import sys
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

# Allowed values, built directly from the Incidents Manager's own enums
# (services/api/incident_models.py). If those change, update these too.
TicketCategory = Literal[
    "equipment_failure",
    "supply_issue",
    "customer_complaint",
    "staff_issue",
    "facility_issue",
    "pos_system",
    "delivery_issue",
    "other",
]
TicketStatus = Literal[
    "open",
    "in_progress",
    "resolved",
    "discarded",
]
TicketOrigin = Literal[
    "customer",
    "branch",
    "internal",
]
TicketBranch = Literal[
    "central",
    "medellin_centro",
    "medellin_laureles",
    "medellin_envigado",
    "medellin_bello",
    "medellin_itagui",
    "bogota_chapinero",
    "bogota_usaquen",
    "cali_granada",
    "barranquilla_norte",
    "miami_doral",
    "miami_hialeah",
    "miami_kendall",
    "orlando_international",
    "fort_lauderdale",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERNAL_API_BASE_URL = os.environ.get("INTERNAL_API_BASE_URL", "http://localhost:8000")
TIMEOUT_SECONDS = 5.0


class Ticket(BaseModel):
    """Mirrors incident_models.Incident's real fields exactly
    (services/api/incident_models.py)."""

    id: int
    title: str
    description: str
    status: str
    category: str
    origin: str
    branch: str
    created_at: str
    updated_at: str


class TicketNotFoundError(Exception):
    pass


class IncidentsServiceUnavailableError(Exception):
    pass


class InvalidTicketDataError(Exception):
    """The Incidents Manager rejected the request as a 400 -- a bad
    field value or an invalid status transition, not a service failure."""


def _mint_service_token() -> str:
    sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
    from security import create_access_token  # noqa: E402

    user_id = os.environ.get("MCP_SERVICE_USER_ID")
    if not user_id:
        raise IncidentsServiceUnavailableError(
            "MCP_SERVICE_USER_ID is not set -- this server has no account to authenticate as."
        )
    return create_access_token(int(user_id))


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_mint_service_token()}"}


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        return httpx.request(
            method,
            f"{INTERNAL_API_BASE_URL}{path}",
            headers=_auth_headers(),
            timeout=TIMEOUT_SECONDS,
            **kwargs,
        )
    except httpx.TimeoutException as exc:
        raise IncidentsServiceUnavailableError(
            f"incident service did not respond within {TIMEOUT_SECONDS}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise IncidentsServiceUnavailableError(f"could not reach incident service: {exc}") from exc


def get_ticket(ticket_id: int) -> Ticket:
    """GET /api/incidents/{ticket_id} -- read-only."""
    response = _request("GET", f"/api/incidents/{ticket_id}")
    if response.status_code == 404:
        raise TicketNotFoundError(f"no ticket with id {ticket_id}")
    if response.status_code != 200:
        raise IncidentsServiceUnavailableError(f"incident service returned {response.status_code}")
    return Ticket(**response.json())


def create_ticket(
    title: str, description: str, category: str, origin: str, branch: str
) -> Ticket:
    """POST /api/incidents -- a brand-new ticket always starts 'open';
    that's a server-side rule in the Incidents Manager itself, not
    something this tool sets."""
    response = _request(
        "POST",
        "/api/incidents",
        json={
            "title": title,
            "description": description,
            "category": category,
            "origin": origin,
            "branch": branch,
        },
    )
    if response.status_code == 400:
        raise InvalidTicketDataError(response.json().get("detail", "invalid ticket data"))
    if response.status_code != 201:
        raise IncidentsServiceUnavailableError(f"incident service returned {response.status_code}")
    return Ticket(**response.json())


def update_ticket_status(ticket_id: int, status: str) -> Ticket:
    """PATCH /api/incidents/{ticket_id}/status -- the Incidents Manager's
    own lifecycle endpoint. This is the ONLY way this server ever changes
    a ticket's status -- never a generic PATCH on the incident resource,
    per the ticket's explicit requirement. The Incidents Manager itself
    enforces which transitions are legal (open -> in_progress/discarded,
    etc.) and returns 400 for an invalid one -- this function doesn't
    duplicate that rule, it just surfaces the real answer."""
    response = _request("PATCH", f"/api/incidents/{ticket_id}/status", json={"status": status})
    if response.status_code == 404:
        raise TicketNotFoundError(f"no ticket with id {ticket_id}")
    if response.status_code == 400:
        raise InvalidTicketDataError(response.json().get("detail", "invalid status transition"))
    if response.status_code != 200:
        raise IncidentsServiceUnavailableError(f"incident service returned {response.status_code}")
    return Ticket(**response.json())
