"""
services/api/agent/mcp_client.py -- the agent's ONLY connection to the
company's ticket and inventory systems: through the MCP server in
mcps/incidents-inventory-tools, as an MCP client.

Before this file existed, the agent called those two systems itself over
plain HTTP. That direct path has been removed on purpose (agent/tools.py
is gone): there is now exactly one way for the agent to reach them, and
it goes through the server's OAuth checks and audit log like any other
client.

How a call works:
  1. get a short-lived access token from the authorization server (Logto)
     using the client-credentials grant, asking only for the scopes the
     agent needs (read-only: it never creates or edits tickets);
  2. connect to the MCP server with that token as a bearer token;
  3. call one named tool and hand back its result.

Everything here is configured from the environment (read at call time,
never hardcoded): MCP_SERVER_URL, LOGTO_TOKEN_URL, MCP_CLIENT_ID,
MCP_CLIENT_SECRET, MCP_RESOURCE_ID, and optionally MCP_SCOPES.

Two kinds of failure, kept apart on purpose so nodes.py can answer
honestly for each:
  MCPToolError        the server answered and said no (ticket not found,
                      missing scope, ...) -- .code holds its error code
  MCPUnavailableError the server or the authorization server could not
                      be reached, timed out, or rejected our token
"""

import asyncio
import json
import os
import time

import httpx
from langchain_core.tools import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

# Numeric timeouts, so a slow or dead server can never hang the graph.
# The MCP server itself gives its backend up to 5 seconds, so the whole
# call gets 10.
CALL_TIMEOUT_SECONDS = 10.0
TOKEN_TIMEOUT_SECONDS = 5.0

_token_cache = {"token": None, "expires_at": 0.0}


class MCPUnavailableError(Exception):
    """The MCP server (or the authorization server) could not be used."""


class MCPToolError(Exception):
    """The MCP server answered, but the tool reported an error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _get_token() -> str:
    """A bearer token for the MCP server, reused until shortly before it
    expires."""
    now = time.monotonic()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    settings = {
        "LOGTO_TOKEN_URL": os.environ.get("LOGTO_TOKEN_URL"),
        "MCP_CLIENT_ID": os.environ.get("MCP_CLIENT_ID"),
        "MCP_CLIENT_SECRET": os.environ.get("MCP_CLIENT_SECRET"),
        "MCP_RESOURCE_ID": os.environ.get("MCP_RESOURCE_ID"),
    }
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise MCPUnavailableError(f"missing configuration: {', '.join(missing)}")

    try:
        response = httpx.post(
            settings["LOGTO_TOKEN_URL"],
            auth=(settings["MCP_CLIENT_ID"], settings["MCP_CLIENT_SECRET"]),
            data={
                "grant_type": "client_credentials",
                "resource": settings["MCP_RESOURCE_ID"],
                # Least privilege: reading only. The agent never needs to
                # create or change tickets.
                "scope": os.environ.get("MCP_SCOPES", "tickets:read inventory:read"),
            },
            timeout=TOKEN_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise MCPUnavailableError(f"could not reach the authorization server: {exc}") from exc
    if response.status_code != 200:
        raise MCPUnavailableError(f"authorization server returned {response.status_code}")

    body = response.json()
    _token_cache["token"] = body["access_token"]
    _token_cache["expires_at"] = now + max(int(body.get("expires_in", 300)) - 30, 0)
    return body["access_token"]


def _as_text(content) -> str:
    """A tool's content arrives as a list of blocks (or a string) --
    flatten it to one piece of text."""
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return str(content)


def _parse(text: str):
    """MCP tool results arrive as JSON text -- turn them back into
    Python data."""
    try:
        result = json.loads(text)
    except ValueError:
        return text
    if isinstance(result, dict) and set(result) == {"result"}:
        result = result["result"]
    return result


def _first_tool_exception(exc):
    """Async connection code can wrap the real error inside an
    ExceptionGroup -- dig the tool's own error back out."""
    if isinstance(exc, ToolException):
        return exc
    for inner in getattr(exc, "exceptions", ()):
        found = _first_tool_exception(inner)
        if found is not None:
            return found
    return None


async def _call(name: str, arguments: dict, token: str):
    client = MultiServerMCPClient(
        {
            "company_tools": {
                "url": os.environ.get("MCP_SERVER_URL", "http://localhost:8100/mcp"),
                "transport": "streamable_http",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )
    tools = await client.get_tools()
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        raise MCPUnavailableError(f"the MCP server does not offer a tool called {name}")
    # Invoked as a tool call (not with bare arguments) on purpose: the
    # adapter turns a tool's error into ordinary-looking text unless the
    # reply comes back as a message whose .status says "error".
    message = await tool.ainvoke({"name": name, "args": arguments, "id": "mcp-call", "type": "tool_call"})
    text = _as_text(message.content)
    if getattr(message, "status", "success") == "error":
        code = text.split(":", 1)[0].strip() if ":" in text else "tool_error"
        raise MCPToolError(code, text)
    return _parse(text)


def call_tool(name: str, arguments: dict):
    """Call one MCP tool and return its result as Python data. Raises
    MCPToolError if the tool reported an error, MCPUnavailableError if
    the server could not be used at all. Synchronous on purpose: the
    graph and its checkpointer are synchronous, and FastAPI runs this
    route in a worker thread with no event loop of its own."""
    token = _get_token()
    try:
        return asyncio.run(asyncio.wait_for(_call(name, arguments, token), timeout=CALL_TIMEOUT_SECONDS))
    except (MCPToolError, MCPUnavailableError):
        raise
    except Exception as exc:  # noqa: BLE001 -- everything else is classified below
        tool_error = _first_tool_exception(exc)
        if tool_error is not None:
            text = str(tool_error)
            code = text.split(":", 1)[0].strip() if ":" in text else "tool_error"
            raise MCPToolError(code, text) from exc
        raise MCPUnavailableError(f"{type(exc).__name__}: {exc}") from exc
