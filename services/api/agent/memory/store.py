"""
services/api/agent/memory/store.py -- where the agent's memory lives.

Backend: Redis (already in the stack from DEV-55), but a SEPARATE database
number (db 1) from Celery's queue (db 0), and every key starts with
"agent_memory:". It never touches the Qdrant `brasaland_knowledge`
collection -- that is the read-only RAG knowledge base.

Four kinds of data, all under the prefix:

    fact:{location}:{category}:{key}   one remembered fact (JSON). The key is a
                                       short topic name like "meat_delivery_days",
                                       so a new value for the same topic REPLACES
                                       the old one instead of piling up beside it.
    pending:{session_id}               the one open proposal for a conversation
    audit                              append-only list of everything that happened
    writes:{user_id}:{yyyymmdd}        how many facts a user saved today (rate limit)

The audit log is append-only by design: this class has no method that edits or
deletes an audit entry, only one that adds them.
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import redis

from . import policy

# Safety net only: the real 10-minute expiry is checked in code (so that an
# expiry can be written to the audit log). Redis drops the key after a day
# in case nothing ever looks at it again.
PENDING_SAFETY_TTL_SECONDS = 24 * 60 * 60

MAX_NOTE_LINES = 12
KEEP_PREVIOUS_VALUES = 3

_ID_MENTION_RE = re.compile(r"\b(col|fla)[-\s]?(\d{2})\b")


def memory_redis_url() -> str:
    """AGENT_MEMORY_REDIS_URL if set; otherwise the same Redis as Celery
    (REDIS_URL) but database 1 instead of 0."""
    explicit = os.getenv("AGENT_MEMORY_REDIS_URL")
    if explicit:
        return explicit
    base = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return urlparse(base)._replace(path="/1").geturl()


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:64]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", policy.fold(text)))


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text)


class MemoryStore:
    def __init__(self, client, *, prefix: str = "agent_memory", clock=None):
        self.client = client
        self.prefix = prefix
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # --- small helpers ------------------------------------------------

    def _now(self) -> datetime:
        return self._clock()

    def _fact_key(self, location: str, category: str, key: str) -> str:
        return f"{self.prefix}:fact:{location}:{category}:{key}"

    def _pending_key(self, session_id: str) -> str:
        return f"{self.prefix}:pending:{_safe_id(session_id)}"

    @property
    def _audit_key(self) -> str:
        return f"{self.prefix}:audit"

    @staticmethod
    def _snapshot(proposal: dict) -> dict:
        return {k: proposal.get(k) for k in
                ("proposal_id", "location", "category", "key", "fact", "replaces", "language", "edited")}

    # --- audit log (append-only) --------------------------------------

    def log(self, event: str, **fields) -> dict:
        entry = {"id": uuid.uuid4().hex, "at": _iso(self._now()), "event": event, **fields}
        self.client.rpush(self._audit_key, json.dumps(entry, ensure_ascii=False, default=str))
        return entry

    def read_audit(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        limit = max(1, min(limit, 500))
        raw = self.client.lrange(self._audit_key, offset, offset + limit - 1)
        return [json.loads(item) for item in raw]

    # --- the one pending proposal --------------------------------------

    def create_pending(self, *, session_id: str, user_id: str, fields: dict, reason: str | None,
                       language: str, origin_message: str) -> dict | None:
        """Opens a proposal. Returns None (and does nothing) if this session
        already has one open -- only one proposal can be pending at a time."""
        if self.get_pending(session_id, user_id) is not None:
            return None
        now = self._now()
        existing = self._load_fact(fields["location"], fields["category"], fields["key"])
        proposal = {
            "proposal_id": uuid.uuid4().hex[:12],
            "session_id": session_id,
            "user_id": user_id,
            **fields,
            "reason": str(reason or "")[:200],
            "language": language,
            "replaces": existing["value"] if existing else None,
            "origin_message": origin_message[:1000],
            "created_at": _iso(now),
            "expires_at": _iso(now + timedelta(minutes=policy.PENDING_TTL_MINUTES)),
            "edited": False,
        }
        # nx=True: only set if no pending key exists, so two requests racing
        # each other still can't open two proposals.
        created = self.client.set(self._pending_key(session_id), json.dumps(proposal, ensure_ascii=False),
                                  nx=True, ex=PENDING_SAFETY_TTL_SECONDS)
        if not created:
            return None
        self.log("proposal_created", proposal_id=proposal["proposal_id"], user_id=user_id,
                 session_id=session_id, proposal=self._snapshot(proposal), origin_message=proposal["origin_message"])
        return proposal

    def get_pending(self, session_id: str, user_id: str) -> dict | None:
        """The open proposal for this conversation, or None. A proposal that
        belongs to a different user is ignored. One past its expiry time is
        discarded (and logged) instead of returned."""
        raw = self.client.get(self._pending_key(session_id))
        if raw is None:
            return None
        proposal = json.loads(raw)
        if proposal.get("user_id") != user_id:
            return None
        if self._now() >= _parse(proposal["expires_at"]):
            self.resolve_pending(session_id, proposal, "discarded_expired", decision_message=None)
            return None
        return proposal

    def edit_pending(self, session_id: str, proposal: dict, new_fact: str, *, decision_message: str) -> dict:
        updated = {**proposal, "fact": new_fact, "edited": True,
                   "expires_at": _iso(self._now() + timedelta(minutes=policy.PENDING_TTL_MINUTES))}
        self.client.set(self._pending_key(session_id), json.dumps(updated, ensure_ascii=False),
                        ex=PENDING_SAFETY_TTL_SECONDS)
        self.log("proposal_edited", proposal_id=proposal["proposal_id"], user_id=proposal["user_id"],
                 session_id=session_id, old_fact=proposal["fact"], new_fact=new_fact,
                 decision_message=decision_message[:1000])
        return updated

    def resolve_pending(self, session_id: str, proposal: dict, outcome: str, *,
                        decision_message: str | None, detail: str | None = None) -> None:
        """Closes the pending proposal and records the outcome: approved,
        rejected, discarded_unclear, discarded_expired, discarded_policy or
        discarded_write_refused. Rejected and discarded ones are logged too."""
        self.client.delete(self._pending_key(session_id))
        self.log("proposal_resolved", proposal_id=proposal["proposal_id"], user_id=proposal["user_id"],
                 session_id=session_id, outcome=outcome, detail=detail,
                 proposal=self._snapshot(proposal), proposal_message=proposal.get("origin_message"),
                 decision_message=(decision_message or "")[:1000] or None)

    # --- facts ----------------------------------------------------------

    def _load_fact(self, location: str, category: str, key: str) -> dict | None:
        raw = self.client.get(self._fact_key(location, category, key))
        return json.loads(raw) if raw else None

    def _save_fact(self, fact: dict) -> None:
        self.client.set(self._fact_key(fact["location"], fact["category"], fact["key"]),
                        json.dumps(fact, ensure_ascii=False))

    def _delete_fact(self, fact: dict) -> None:
        self.client.delete(self._fact_key(fact["location"], fact["category"], fact["key"]))

    def _scan_facts(self, pattern: str) -> list[dict]:
        facts = []
        for redis_key in self.client.scan_iter(match=pattern, count=200):
            raw = self.client.get(redis_key)
            if raw:
                facts.append(json.loads(raw))
        return facts

    def all_facts(self) -> list[dict]:
        return sorted(self._scan_facts(f"{self.prefix}:fact:*"),
                      key=lambda f: (f["location"], f["category"], f["key"]))

    def facts_for_location(self, location: str) -> list[dict]:
        return self._scan_facts(f"{self.prefix}:fact:{location}:*")

    def _writes_today(self, user_id: str) -> int:
        return int(self.client.get(f"{self.prefix}:writes:{_safe_id(user_id)}:{self._now():%Y%m%d}") or 0)

    def _count_write(self, user_id: str) -> None:
        key = f"{self.prefix}:writes:{_safe_id(user_id)}:{self._now():%Y%m%d}"
        self.client.incr(key)
        self.client.expire(key, 2 * 24 * 60 * 60)

    def write_fact(self, proposal: dict, *, decision_message: str) -> dict:
        """Saves an approved proposal. Returns {"status": "written", ...} or
        {"status": "refused", "reason": ...}. This is the ONLY place a fact is
        written, and it re-checks the content rules, so nothing can bypass them."""
        user_id = proposal["user_id"]
        clean, why = policy.validate_proposal(proposal)
        if clean is None:
            self.log("memory_refused", proposal_id=proposal["proposal_id"], user_id=user_id, reason=why)
            return {"status": "refused", "reason": why}
        if self._writes_today(user_id) >= policy.MAX_WRITES_PER_USER_PER_DAY:
            self.log("memory_refused", proposal_id=proposal["proposal_id"], user_id=user_id, reason="rate_limited")
            return {"status": "refused", "reason": "rate_limited"}

        now = _iso(self._now())
        existing = self._load_fact(clean["location"], clean["category"], clean["key"])
        fact = {
            "location": clean["location"], "category": clean["category"], "key": clean["key"],
            "value": clean["fact"], "language": proposal.get("language", "en"),
            "created_at": existing["created_at"] if existing else now,
            "confirmed_at": now, "last_seen": now, "times_seen": 1, "stale": False,
            "approved_by": user_id, "proposal_id": proposal["proposal_id"], "previous": [],
        }
        replaced = None
        if existing:
            replaced = existing["value"]
            fact["previous"] = (existing.get("previous", []) +
                                [{"value": existing["value"], "replaced_at": now}])[-KEEP_PREVIOUS_VALUES:]
            if clean["category"] == "known_incidents":
                # The same incident happening again: count it instead of adding a copy.
                fact["times_seen"] = existing.get("times_seen", 1) + 1
        self._save_fact(fact)
        self._count_write(user_id)
        self.log("memory_written", proposal_id=proposal["proposal_id"], user_id=user_id,
                 location=fact["location"], category=fact["category"], key=fact["key"],
                 value=fact["value"], replaced_value=replaced, decision_message=decision_message[:1000])
        self.consolidate(location=fact["location"])
        return {"status": "written", "fact": fact, "replaced": replaced}

    # --- reading memory for a question ---------------------------------

    def relevant_facts(self, question: str) -> list[dict]:
        """Facts about the locations this question mentions -- by name
        ("Medellín centro"), by id ("COL-07"), or a whole city ("Medellín").
        If a specific restaurant is mentioned, facts saved for its whole city
        come along too. No location mentioned means no facts are loaded."""
        facts = self.all_facts()
        if not facts:
            return []
        question_tokens = _tokens(question)
        stored_locations = {f["location"] for f in facts}
        matched = {loc for loc in stored_locations if set(loc.split("_")) <= question_tokens}
        for prefix, number in _ID_MENTION_RE.findall(policy.fold(question)):
            slug = policy.BRANCH_SLUGS.get(f"{prefix.upper()}-{number}")
            if slug:
                matched.add(slug)
        for loc in list(matched):
            city = loc.split("_")[0]
            if city != loc and city in stored_locations:
                matched.add(city)
        return [f for f in facts if f["location"] in matched]

    # --- consolidation / cleanup ---------------------------------------

    def _sweep_pending(self) -> int:
        expired = 0
        now = self._now()
        for redis_key in self.client.scan_iter(match=f"{self.prefix}:pending:*", count=200):
            raw = self.client.get(redis_key)
            if not raw:
                continue
            proposal = json.loads(raw)
            if now >= _parse(proposal["expires_at"]):
                self.resolve_pending(proposal["session_id"], proposal, "discarded_expired", decision_message=None)
                expired += 1
        return expired

    def consolidate(self, *, location: str | None = None) -> dict:
        """Keeps memory from growing without limit. Runs after every write
        (for that one location) and can be run for everything with
        scripts/agent_memory_consolidate.py. What it does:
          1. drops unanswered proposals older than 10 minutes (logged)
          2. forgets known_incidents not seen again in 90 days
          3. flags hours/suppliers/prefs not re-confirmed in 180 days as
             "may be outdated" (they stay, but are labelled)
          4. trims each fact's history of old values to the last 3
          5. enforces a cap of 40 facts per location, dropping incidents
             first, then outdated facts, then the least recently confirmed
        Every removal is written to the audit log."""
        summary = {"expired_proposals": self._sweep_pending(), "expired_incidents": 0,
                   "flagged_outdated": 0, "evicted": 0}
        now = self._now()
        facts = self.all_facts() if location is None else self.facts_for_location(location)

        by_location: dict[str, list[dict]] = {}
        for fact in facts:
            if (fact["category"] == "known_incidents"
                    and now - _parse(fact["last_seen"]) > timedelta(days=policy.INCIDENT_EXPIRY_DAYS)):
                self._delete_fact(fact)
                self.log("memory_expired", location=fact["location"], category=fact["category"],
                         key=fact["key"], value=fact["value"], last_seen=fact["last_seen"])
                summary["expired_incidents"] += 1
                continue
            changed = False
            if len(fact.get("previous", [])) > KEEP_PREVIOUS_VALUES:
                fact["previous"] = fact["previous"][-KEEP_PREVIOUS_VALUES:]
                changed = True
            if (fact["category"] != "known_incidents" and not fact.get("stale")
                    and now - _parse(fact["confirmed_at"]) > timedelta(days=policy.RECONFIRM_AFTER_DAYS)):
                fact["stale"] = True
                changed = True
                self.log("memory_flagged_outdated", location=fact["location"], category=fact["category"],
                         key=fact["key"], confirmed_at=fact["confirmed_at"])
                summary["flagged_outdated"] += 1
            if changed:
                self._save_fact(fact)
            by_location.setdefault(fact["location"], []).append(fact)

        for loc, items in by_location.items():
            over = len(items) - policy.MAX_FACTS_PER_LOCATION
            if over <= 0:
                continue
            items.sort(key=lambda f: (0 if f["category"] == "known_incidents" else 1 if f.get("stale") else 2,
                                      f["confirmed_at"]))
            for victim in items[:over]:
                self._delete_fact(victim)
                self.log("memory_evicted", location=loc, category=victim["category"], key=victim["key"],
                         value=victim["value"], reason="location_over_cap")
                summary["evicted"] += 1
        return summary


def format_notes(facts: list[dict]) -> list[str]:
    """Turns facts into the short lines the model sees, grouped by
    location + category (one line per group)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for fact in facts:
        groups.setdefault((fact["location"], fact["category"]), []).append(fact)
    lines = []
    for (location, category), items in groups.items():
        parts = []
        for fact in items:
            text = fact["value"]
            if fact.get("times_seen", 1) > 1:
                text += f" (happened {fact['times_seen']} times, last on {fact['last_seen'][:10]})"
            if fact.get("stale"):
                text += f" (not re-confirmed in over {policy.RECONFIRM_AFTER_DAYS} days; may be outdated)"
            parts.append(text)
        lines.append(f"[{location} / {category}] " + " | ".join(parts))
    return lines[:MAX_NOTE_LINES]


# --- the shared store used by the graph --------------------------------------

_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        client = redis.Redis.from_url(memory_redis_url(), decode_responses=True,
                                      socket_connect_timeout=2, socket_timeout=2)
        _store = MemoryStore(client)
    return _store


def set_store(store: MemoryStore | None) -> None:
    """Swap the shared store (tests and the evidence script use this)."""
    global _store
    _store = store
