# Brasaland Incidents & Inventory MCP Server

An MCP server that lets any authorized MCP client work with the company's
Incidents Manager and Inventory Manager through five tools, without
knowing anything about the backend code. Access is protected by OAuth.

## How it's built

| Piece | Choice |
|---|---|
| Transport | Streamable HTTP |
| Authentication | OAuth 2.1 / OIDC through MCP Auth (`mcpauth`), resource-server mode, with Logto as the authorization server |
| Framework | FastMCP |

**Why Streamable HTTP, not stdio.** stdio only works when one client starts
the server itself on the same machine, and it has no place to carry an
`Authorization` header, so OAuth tokens don't fit. This server is meant to
be reused by other agents and teams over the network, so it needs a real
URL. Testing it in MCP Playground through a public URL points the same way.

**How authentication works.**
- A client asks Logto for an access token (client-credentials grant) for this
  server's resource identifier and the scopes it needs.
- The server validates the bearer JWT against Logto's public keys. No valid
  token means no access, not even to list tools.
- The server publishes its Protected Resource Metadata (RFC 9728) at
  `/.well-known/oauth-protected-resource/incidents-inventory`. This address is
  public on purpose, so a client can find out where to get a token.
- Each tool then checks its own scope (least privilege). A token that can read
  inventory cannot touch tickets.
- Separately, when a tool calls the Incidents Manager, the server signs a
  short-lived JWT with the app's existing `create_access_token()` for a
  service-account user (`MCP_SERVICE_USER_ID`). There are two layers of auth:
  client to MCP server (OAuth), and MCP server to Incidents Manager (the
  app's own JWT).

## Tools and permissions

Every tool's description and input schema are visible through standard MCP
discovery (`tools/list`), so a client doesn't need this file or the source.

| Tool | What it does | Scope needed | Backend call |
|---|---|---|---|
| `check_ticket_status` | Read one ticket by ID | `tickets:read` | `GET /api/incidents/{id}` |
| `create_ticket` | Create a ticket (always starts `open`) | `tickets:write` | `POST /api/incidents` |
| `update_ticket_status` | Move a ticket to a new status | `tickets:write` | `PATCH /api/incidents/{id}/status` |
| `query_inventory` | List products, optionally filtered by name | `inventory:read` | `GET /inventory/products` |
| `update_inventory_stock` | Always rejected (see below) | none | none, it never calls anything |

- Status changes only go through the Incidents Manager's lifecycle endpoint,
  never a generic edit. The Incidents Manager decides which moves are legal.
- `category`, `origin`, `branch`, and `status` only accept the values the
  Incidents Manager defines. Anything else is rejected before the backend is
  called, and the allowed values are listed in the tool's schema.
- Inventory is read-only by design. `update_inventory_stock` is listed in
  discovery on purpose so that a write attempt gets a clear, explicit
  rejection, not a missing feature. No scope allows it.

## Errors

Authentication failures are plain HTTP `401` responses. Everything else comes
back as an MCP tool error (the HTTP request succeeds and the result is
flagged as an error), with a code at the start of the message.

| Where | Code or message | When |
|---|---|---|
| HTTP 401 | JSON with `error` (for example `missing_auth_header`) and `error_description` | No token, or an invalid or expired one |
| Tool error | `insufficient_scope` | The token is valid but lacks the scope this tool needs. The message names the needed scope and the scopes the token has |
| Tool error | Input validation message listing the allowed values | Bad `category`, `origin`, `branch`, or `status` |
| Tool error | `invalid_ticket_data` | The Incidents Manager returned 400, such as an illegal status move. Its own message is passed through |
| Tool error | `ticket_not_found` | No ticket with that ID |
| Tool error | `read_only_violation` | Any attempt to modify inventory, whatever the scopes |
| Tool error | `incidents_service_unavailable` or `inventory_service_unavailable` | The backend did not answer within 5 seconds, or returned an error |

## Logging

Every tool call writes one line to the server's output: which tool, which
client, the arguments, and the result. Example:

```
tool=query_inventory client=<client id> args={'product_name': 'brisket'} result=success duration_ms=44.2
```

Failed calls log `result=error` with the error. One known gap: a call rejected
by input validation never reaches the tool code, so FastMCP logs it as a
warning without the client name.

## Running it

The real API has to be running too, since the tools call it:

```bash
# terminal 1: the real API (Incidents and Inventory endpoints)
cd services/api
uv run uvicorn main:app --reload

# terminal 2: this server
cd mcps/incidents-inventory-tools
uv sync
uv run --env-file .env python server.py
```

Create `mcps/incidents-inventory-tools/.env` (not committed):

| Variable | Meaning |
|---|---|
| `LOGTO_ISSUER_URL` | The Logto tenant's OIDC issuer, `https://<tenant>.logto.app/oidc` |
| `MCP_RESOURCE_ID` | The API resource identifier registered in Logto |
| `MCP_SERVICE_USER_ID` | A real user id from `services/api`, used for the server's own calls to the Incidents Manager |
| `INTERNAL_API_BASE_URL` | Where the real API runs (default `http://localhost:8000`) |
| `MCP_SERVER_PORT` | Port for this server (default `8100`) |

`mcpauth` must be version 0.2.0b1 or newer. Earlier releases don't support
Protected Resource Metadata.

To get a test token:

```bash
curl -X POST <LOGTO_ISSUER_URL>/token \
  -u "<APP_ID>:<APP_SECRET>" \
  -d "grant_type=client_credentials" \
  -d "resource=<MCP_RESOURCE_ID>" \
  -d "scope=tickets:read tickets:write inventory:read"
```

## Validation in MCP Playground

Tested with https://www.mcpplayground.tech/connect using the public Codespaces
forwarded URL (port 8100 set to Public), not localhost:
`https://<codespace>-8100.app.github.dev/mcp`. Transport: Streamable HTTP.
Authentication: an `Authorization: Bearer <token>` header with a token from
Logto. The site connected and listed 5 tools, 0 resources, 0 prompts.

| Tool | Input | Result |
|---|---|---|
| `check_ticket_status` | ticket 1 | Ticket 1, status `open` |
| `create_ticket` | "POS terminal offline", `pos_system`, `branch`, `medellin_centro` | Ticket 3 created, status `open` |
| `update_ticket_status` | ticket 1 to `in_progress` | Status `in_progress` |
| `update_ticket_status` | ticket 1 to `resolved` | Status `resolved` |
| `update_ticket_status` | ticket 1 to `open` | Rejected (see below) |
| `query_inventory` | `product_name: brisket` | 1 product: Beef brisket, 62.0 kg |
| `query_inventory` | no input | All 7 products |
| `update_inventory_stock` | any values | Rejected (see below) |

Illegal status move, rejected by the Incidents Manager and passed through:

```
invalid_ticket_data: {'field': 'status', 'message': "Cannot move an incident from 'resolved' to 'open'."}
```

Inventory write attempt, rejected by this server:

```
read_only_violation: this server never modifies inventory data, regardless of scope. Use query_inventory to read stock levels.
```

<details>
<summary>Raw results</summary>

Create ticket:

```json
{"id":3,"title":"POS terminal offline","description":"POS down at Location 1","status":"open","category":"pos_system","origin":"branch","branch":"medellin_centro","created_at":"2026-09-28T01:48:00.530842Z","updated_at":"2026-09-28T01:48:00.530842Z"}
```

Check ticket (ticket 1, before any status change):

```json
{"id":1,"title":"POS terminal offline","description":"Terminal 2 not responding at checkout","status":"open","category":"pos_system","origin":"branch","branch":"medellin_centro","created_at":"2026-09-24T15:42:56.784940Z","updated_at":"2026-09-24T15:42:56.784940Z"}
```

Update ticket 1 to `in_progress`, then `resolved`:

```json
{"id":1,"title":"POS terminal offline","description":"Terminal 2 not responding at checkout","status":"in_progress","category":"pos_system","origin":"branch","branch":"medellin_centro","created_at":"2026-09-24T15:42:56.784940Z","updated_at":"2026-09-28T01:50:04.833629Z"}
{"id":1,"title":"POS terminal offline","description":"Terminal 2 not responding at checkout","status":"resolved","category":"pos_system","origin":"branch","branch":"medellin_centro","created_at":"2026-09-24T15:42:56.784940Z","updated_at":"2026-09-28T01:50:24.642558Z"}
```

Query inventory (`product_name: brisket`, then no input):

```json
[{"id":1,"name":"Beef brisket","sku":"BRS-BEEF-001","unit":"kg","category":"meat","country":"CO","current_stock":62.0,"minimum_stock":null}]
[{"id":1,"name":"Beef brisket","sku":"BRS-BEEF-001","unit":"kg","category":"meat","country":"CO","current_stock":62.0,"minimum_stock":null},{"id":2,"name":"Pork ribs","sku":"BRS-PORK-001","unit":"kg","category":"meat","country":"US","current_stock":25.0,"minimum_stock":null},{"id":3,"name":"Chimichurri sauce","sku":"BRS-SAUCE-001","unit":"litre","category":"sauce","country":"CO","current_stock":17.0,"minimum_stock":null},{"id":4,"name":"House BBQ sauce","sku":"BRS-SAUCE-002","unit":"litre","category":"sauce","country":"US","current_stock":10.5,"minimum_stock":null},{"id":5,"name":"Yuca (cassava)","sku":"BRS-PROD-001","unit":"kg","category":"produce","country":"CO","current_stock":25.0,"minimum_stock":null},{"id":6,"name":"Takeaway box (M)","sku":"BRS-PKG-001","unit":"unit","category":"packaging","country":"CO","current_stock":200.0,"minimum_stock":null},{"id":8,"name":"Crema","sku":"BRS-SAUCE-003","unit":"oz","category":"sauce","country":"USA","current_stock":6.0,"minimum_stock":null}]
```

</details>
