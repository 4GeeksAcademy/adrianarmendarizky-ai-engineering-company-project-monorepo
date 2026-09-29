"""
services/api/agent/guardrails/telemetry.py -- Milestone 8 Part 2 (SEC-114):
minimal observability for the guardrail harness.

Every guardrail block or redirection is logged here with its failure
type -- "structural", "content", or "security", the same three ways the
ticket's own harness note says agents fail -- and a short reason code
(e.g. "instruction_change", "poisoned_rag_content", "empty_answer").

Uses the SAME Redis connection helper as agent memory
(agent/memory/store.py's memory_redis_url(): Celery's own db 0, agent
data in db 1), under its own key prefix ("guardrails:") so it never
mixes with memory's facts or audit log. GET /agent/guardrails/summary
and GET /agent/guardrails/events (routes/agent.py) are the "simple
summary" and full log the ticket asks for.
"""

import json
import uuid
from datetime import datetime, timezone

import redis

from agent.memory.store import memory_redis_url

PREFIX = "guardrails"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            memory_redis_url(), decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
    return _client


def set_client(client) -> None:
    """Swap the Redis client (tests use this)."""
    global _client
    _client = client


def log_event(category: str, reason: str, **fields) -> dict | None:
    """category: "structural" | "content" | "security". Never raises --
    a guardrail decision has already been made by the time this is
    called, and a logging outage must never undo or block that decision.
    It just means this one event goes unrecorded, same as Part 1's
    memory audit log handles a Redis outage."""
    entry = {
        "id": uuid.uuid4().hex,
        "at": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "reason": reason,
        **fields,
    }
    try:
        client = _get_client()
        client.rpush(f"{PREFIX}:events", json.dumps(entry, ensure_ascii=False, default=str))
        client.hincrby(f"{PREFIX}:counts", f"{category}:{reason}", 1)
    except redis.exceptions.RedisError:
        return None
    return entry


def read_events(*, limit: int = 200, offset: int = 0) -> list[dict]:
    limit = max(1, min(limit, 500))
    client = _get_client()
    raw = client.lrange(f"{PREFIX}:events", offset, offset + limit - 1)
    return [json.loads(item) for item in raw]


def summary() -> dict:
    """{"total": N, "by_category": {"security": 4, "content": 6, ...},
    "by_reason": {"security:instruction_change": 4, ...}} -- the simple
    trigger-count summary the ticket asks for."""
    client = _get_client()
    by_reason = {k: int(v) for k, v in client.hgetall(f"{PREFIX}:counts").items()}
    by_category: dict[str, int] = {}
    for key, count in by_reason.items():
        category = key.split(":", 1)[0]
        by_category[category] = by_category.get(category, 0) + count
    return {"total": sum(by_reason.values()), "by_category": by_category, "by_reason": by_reason}
