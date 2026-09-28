"""
mcps/incidents-inventory-tools/audit_log.py -- one log line per tool
invocation, with which tool, which client, and what result -- the
ticket's explicit traceability requirement.

A plain logger to stdout (captured by whatever runs this process --
uvicorn's own logging, a Codespace terminal, or a container's log
driver) rather than a bespoke log file: this server is meant to be run
like any other process in this monorepo, and every other service here
already logs to stdout, not a custom file path.
"""

import functools
import logging
import time

from mcpauth import MCPAuth

logger = logging.getLogger("mcp_tools.audit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def audited_tool(mcp_auth: MCPAuth):
    """Decorator factory: wraps a tool function so every call logs
    (client_id, tool name, arguments, and outcome -- success or the
    specific error) exactly once, whether the tool succeeds, is denied
    for an insufficient scope, or fails for any other reason. Applied to
    every tool in server.py -- there's no tool that skips this."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            info = mcp_auth.auth_info
            client_id = (info.client_id or info.subject) if info else "unknown"
            started = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                logger.info(
                    "tool=%s client=%s args=%s result=success duration_ms=%.1f",
                    fn.__name__,
                    client_id,
                    kwargs,
                    (time.monotonic() - started) * 1000,
                )
                return result
            except Exception as exc:
                logger.info(
                    "tool=%s client=%s args=%s result=error error=%s duration_ms=%.1f",
                    fn.__name__,
                    client_id,
                    kwargs,
                    repr(exc),
                    (time.monotonic() - started) * 1000,
                )
                raise

        return wrapper

    return decorator
