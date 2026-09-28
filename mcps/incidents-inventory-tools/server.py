"""
mcps/incidents-inventory-tools/server.py -- the MCP Server itself.

Exposes the Incidents Manager and Inventory Manager as MCP tools, over
Streamable HTTP, protected by OAuth via MCP Auth (mcpauth) -- not
FastMCP's own built-in auth layer, per the ticket's explicit
requirement, so the authorization flow matches the real MCP
authorization spec (Protected Resource Metadata / RFC 9728, a
resource-server mode pointed at a real OIDC provider) rather than a
framework-specific shortcut.

Transport: Streamable HTTP, not stdio. Two reasons, not one: (1) OAuth
bearer tokens are carried in an HTTP Authorization header -- stdio has
no equivalent, so token-based auth and stdio don't really combine; (2)
this server is explicitly meant to be reusable by other agents/teams,
which means a real network endpoint, not a subprocess one client
spawns locally. MCP Playground's own requirement to connect over a
public URL rather than localhost confirms the same thing from the
testing side.

Authorization server: Logto (OIDC), configured via LOGTO_ISSUER_URL and
MCP_RESOURCE_ID below -- see the project setup notes for how those were
obtained.

Least privilege: each tool checks its OWN required scope at call time
(require_scope()) -- the bearer_auth_middleware below only enforces
"some valid token," not which scopes it carries, because a single
Streamable HTTP mount can't express "this tool needs scope X, this
other tool needs scope Y" as one blanket check. This is the same reason
audited_tool() wraps every tool individually rather than logging once
at the transport layer: per-call correctness lives per-call.
"""

import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.types import ResourceServerConfig, ResourceServerMetadata
from mcpauth.utils import fetch_server_config
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount

import incidents_client as incidents
from incidents_client import TicketBranch, TicketCategory, TicketOrigin, TicketStatus
import inventory_client as inventory
from audit_log import audited_tool

LOGTO_ISSUER_URL = os.environ["LOGTO_ISSUER_URL"]  # e.g. https://9tftyv.logto.app/oidc
MCP_RESOURCE_ID = os.environ["MCP_RESOURCE_ID"]  # e.g. https://brasaland-mcp.local/incidents-inventory
MCP_SERVER_PORT = int(os.environ.get("MCP_SERVER_PORT", "8100"))

auth_server_config = fetch_server_config(LOGTO_ISSUER_URL, AuthServerType.OIDC)

mcp_auth = MCPAuth(
    protected_resources=ResourceServerConfig(
        metadata=ResourceServerMetadata(
            resource=MCP_RESOURCE_ID,
            authorization_servers=[auth_server_config],
            scopes_supported=["tickets:read", "tickets:write", "inventory:read"],
            resource_name="Brasaland Incidents & Inventory",
            resource_documentation="https://brasaland-mcp.local/docs",
        )
    )
)

mcp = FastMCP("brasaland-incidents-inventory")

audited = audited_tool(mcp_auth)


def require_scope(scope: str) -> None:
    """Least-privilege check for one tool. Raises ToolError (a clean,
    client-visible MCP tool error -- see fastmcp.exceptions.ToolError,
    never a raw traceback) when the caller's token doesn't carry the
    scope this specific tool needs, even though it cleared the bearer
    middleware's "some valid token" check to get this far."""
    info = mcp_auth.auth_info
    granted = (info.scopes if info else []) or []
    if scope not in granted:
        raise ToolError(
            f"insufficient_scope: this tool requires the '{scope}' scope; "
            f"your token carries {granted or '(no scopes)'}"
        )


# --- Incidents Manager tools -------------------------------------------


@mcp.tool
@audited
def check_ticket_status(ticket_id: int) -> dict:
    """Look up one support ticket by its numeric ID in the real
    Incidents Manager. Read-only. Requires the 'tickets:read' scope.

    Returns the ticket's id, title, description, status, category,
    origin, branch, and timestamps -- exactly the fields the Incidents
    Manager itself returns, nothing added or renamed.

    Raises a clean, explained error (not a raw exception) if: the token
    lacks 'tickets:read' (insufficient_scope), no ticket with that ID
    exists (ticket_not_found), or the Incidents Manager doesn't respond
    within 5 seconds or errors (incidents_service_unavailable)."""
    require_scope("tickets:read")
    try:
        return incidents.get_ticket(ticket_id).model_dump()
    except incidents.TicketNotFoundError:
        raise ToolError(f"ticket_not_found: no ticket with id {ticket_id}")
    except incidents.IncidentsServiceUnavailableError as exc:
        raise ToolError(f"incidents_service_unavailable: {exc}")


@mcp.tool
@audited
def create_ticket(
    title: str,
    description: str,
    category: TicketCategory,
    origin: TicketOrigin,
    branch: TicketBranch,
) -> dict:
    """Create a new support ticket in the real Incidents Manager.
    Requires the 'tickets:write' scope. A new ticket always starts with
    status 'open' -- that's set by the Incidents Manager itself, not a
    choice this tool makes.

    category, origin, and branch accept only the exact values the
    Incidents Manager itself defines -- each field's allowed values are
    listed in this tool's input schema, and anything else is rejected
    before the Incidents Manager is called.

    Raises a clean error if: the token lacks 'tickets:write'
    (insufficient_scope), any field is invalid (invalid_ticket_data,
    with the Incidents Manager's own field-level message), or the
    service doesn't respond (incidents_service_unavailable)."""
    require_scope("tickets:write")
    try:
        return incidents.create_ticket(title, description, category, origin, branch).model_dump()
    except incidents.InvalidTicketDataError as exc:
        raise ToolError(f"invalid_ticket_data: {exc}")
    except incidents.IncidentsServiceUnavailableError as exc:
        raise ToolError(f"incidents_service_unavailable: {exc}")


@mcp.tool
@audited
def update_ticket_status(ticket_id: int, status: TicketStatus) -> dict:
    """Move a ticket to a new status in the real Incidents Manager, via
    its own lifecycle endpoint (PATCH /api/incidents/{id}/status) --
    never a generic edit of the ticket record. Requires the
    'tickets:write' scope.

    status must be one of: open, in_progress, resolved, discarded. The
    Incidents Manager enforces which transitions are legal from the
    ticket's current status (e.g. resolved and discarded are final) --
    this tool does not duplicate or second-guess that rule.

    Raises a clean error if: the token lacks 'tickets:write'
    (insufficient_scope), no ticket with that ID exists
    (ticket_not_found), the transition isn't allowed from the ticket's
    current status (invalid_ticket_data), or the service doesn't
    respond (incidents_service_unavailable)."""
    require_scope("tickets:write")
    try:
        return incidents.update_ticket_status(ticket_id, status).model_dump()
    except incidents.TicketNotFoundError:
        raise ToolError(f"ticket_not_found: no ticket with id {ticket_id}")
    except incidents.InvalidTicketDataError as exc:
        raise ToolError(f"invalid_ticket_data: {exc}")
    except incidents.IncidentsServiceUnavailableError as exc:
        raise ToolError(f"incidents_service_unavailable: {exc}")


# --- Inventory Manager tool (read-only) --------------------------------


@mcp.tool
@audited
def query_inventory(product_name: str | None = None) -> list[dict]:
    """List products in the real Inventory Manager, optionally filtered
    to names containing `product_name` (case-insensitive substring
    match against the real catalog). Read-only. Requires the
    'inventory:read' scope.

    Returns each matching product's id, name, sku, unit, category,
    country, current_stock, and minimum_stock.

    Raises a clean error if: the token lacks 'inventory:read'
    (insufficient_scope), or the service doesn't respond
    (inventory_service_unavailable)."""
    require_scope("inventory:read")
    try:
        items = inventory.query_products(product_name)
    except inventory.InventoryServiceUnavailableError as exc:
        raise ToolError(f"inventory_service_unavailable: {exc}")
    return [item.model_dump() for item in items]


@mcp.tool
@audited
def update_inventory_stock(product_id: int, quantity: float) -> dict:
    """NOT SUPPORTED. This server enforces read-only access to
    inventory data -- this tool exists in discovery on purpose, so that
    an attempted write is a clear, documented, always-on rejection
    (read_only_violation) rather than a capability that's simply
    missing and easy to mistake for a bug. No scope grants this
    operation; it is rejected unconditionally, before any inventory
    system is ever touched."""
    raise ToolError(
        "read_only_violation: this server never modifies inventory data, regardless of scope. "
        "Use query_inventory to read stock levels."
    )


# --- OAuth wiring --------------------------------------------------------

bearer_auth = Middleware(mcp_auth.bearer_auth_middleware("jwt", resource=MCP_RESOURCE_ID))

mcp_asgi = mcp.http_app(path="/mcp", middleware=[bearer_auth])

app = Starlette(
    routes=[
        # Protected Resource Metadata (RFC 9728) is deliberately NOT
        # behind bearer_auth: a client has to be able to fetch this
        # before it has a token, to learn where to get one.
        *mcp_auth.resource_metadata_router().routes,
        Mount("/", app=mcp_asgi),
    ],
    lifespan=mcp_asgi.lifespan,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=MCP_SERVER_PORT)
