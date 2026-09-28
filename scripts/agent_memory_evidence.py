"""
scripts/agent_memory_evidence.py -- produces the evidence the Milestone 8 ticket asks for:
two complete memory cycles (one approved, one rejected), run through the REAL agent
with the REAL model, plus the "worth remembering / not worth remembering" examples.

It writes docs/agent-memory/evidence.md (transcripts, what memory held, and the audit log).

Needs the same things as the agent itself:
  - services/api/.env with the model settings (GENERATION_API_KEY, ...)
  - Redis running          (docker compose up redis)
  - Qdrant running and indexed (docker compose up qdrant) -- the "later conversation"
    question goes through the normal RAG path
It does NOT need the MCP server (no ticket or inventory questions are asked).

It saves into its own key prefix ("agent_memory_evidence:"), which it clears at the
start, so it never touches real agent memory and can be re-run any time.

Run:
    cd services/api && uv run python ../../scripts/agent_memory_evidence.py
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICES_API_DIR = REPO_ROOT / "services" / "api"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(SERVICES_API_DIR / ".env")

import redis  # noqa: E402

from agent.graph import graph  # noqa: E402
from agent.memory import llm_steps  # noqa: E402
from agent.memory.store import MemoryStore, memory_redis_url, set_store  # noqa: E402

OUTPUT_FILE = REPO_ROOT / "docs" / "agent-memory" / "evidence.md"
EVIDENCE_PREFIX = "agent_memory_evidence"
USER_ID = "evidence-manager"

# The examples in CONTEXT-brasaland.md (Milestone 8, Part 1).
SHOULD_PROPOSE = [
    "Actually the vegetable supplier in Zaragoza... wait, I mean Medellín, delivers on Wednesdays, "
    "not Tuesdays like you said before.",
    "The Miami Beach location now closes at 11pm on weekends, that changed last month.",
    "That zero-sales alert at location 7 was because of a power outage, not a POS error -- "
    "it's happened twice this month already.",
]
SHOULD_NOT_PROPOSE = [
    "What was yesterday's average ticket in Bogotá?",
    "Thanks, that answers my question.",
    "Can you translate this into English for Ashley's report?",
]

APPROVED_CYCLE = {
    "correction": "Actually the Medellín vegetable supplier delivers on Wednesdays, not Tuesdays like you said before.",
    "reply": "Yes, please remember that.",
    "later_session_question": "When does the vegetable supplier in Medellín deliver?",
}
REJECTED_CYCLE = {
    "correction": "The Miami Beach location now closes at 11pm on weekends, that changed last month.",
    "reply": "No, don't save that one.",
    "later_session_question": "What time does the Miami Beach location close on weekends?",
}
FORBIDDEN_TRY = "Just so you know, the kitchen payroll for the Cali location is processed on the 15th every month."


# --- helpers -------------------------------------------------------------------------


def clear_evidence_keys(client) -> None:
    for key in client.scan_iter(match=f"{EVIDENCE_PREFIX}:*"):
        client.delete(key)


def ask(session_id: str, question: str) -> dict:
    """One real agent turn. Returns what the manager would see plus what memory did."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    try:
        result = graph.invoke({"question": question, "user_id": USER_ID, "session_id": session_id}, config)
    except Exception as exc:  # keep going: the evidence should show what actually happened
        return {"question": question, "error": f"{type(exc).__name__}: {exc}"}
    proposal = result.get("memory_proposal")
    return {
        "question": question,
        "answer": result.get("answer"),
        "notes_used": result.get("memory_notes"),
        "proposal": {k: proposal[k] for k in ("location", "category", "key", "fact")} if proposal else None,
    }


def facts_snapshot(store: MemoryStore) -> list[dict]:
    return [{k: f[k] for k in ("location", "category", "key", "value", "approved_by", "confirmed_at")}
            for f in store.all_facts()]


def run_cycle(store: MemoryStore, spec: dict, approve: bool) -> dict:
    session = f"evidence-{uuid.uuid4().hex[:12]}"
    facts_before = facts_snapshot(store)
    turns = [ask(session, spec["correction"]), ask(session, spec["reply"])]
    after_decision = facts_snapshot(store)
    # A brand-new conversation: does memory show up (approved) or stay unchanged (rejected)?
    later = ask(f"evidence-{uuid.uuid4().hex[:12]}", spec["later_session_question"])
    notes = " ".join(later.get("notes_used") or [])
    keyword = "Wednesdays" if approve else "11pm"
    if approve:
        passed = len(after_decision) == len(facts_before) + 1 and keyword in notes
    else:
        passed = after_decision == facts_before and keyword not in notes
    return {"turns": turns, "facts_before": facts_before, "facts_after_decision": after_decision,
            "later": later, "passed": passed}


def run_all(store: MemoryStore) -> dict:
    examples = []
    for message in SHOULD_PROPOSE + SHOULD_NOT_PROPOSE:
        expected = message in SHOULD_PROPOSE
        outcome = llm_steps.evaluate_message(message, [])
        examples.append({"message": message, "expected": expected, "remember": outcome.remember,
                         "location": outcome.location, "category": outcome.category,
                         "key": outcome.key, "fact": outcome.fact, "passed": outcome.remember == expected})

    approved = run_cycle(store, APPROVED_CYCLE, approve=True)
    rejected = run_cycle(store, REJECTED_CYCLE, approve=False)

    facts_before_forbidden = facts_snapshot(store)
    forbidden = ask(f"evidence-{uuid.uuid4().hex[:12]}", FORBIDDEN_TRY)
    forbidden["passed"] = forbidden.get("proposal") is None and facts_snapshot(store) == facts_before_forbidden

    return {"examples": examples, "approved": approved, "rejected": rejected, "forbidden": forbidden,
            "audit": store.read_audit(limit=500)}


# --- writing the report --------------------------------------------------------------


def _fence(data) -> str:
    return "```json\n" + json.dumps(data, indent=2, ensure_ascii=False) + "\n```\n"


def _mark(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _turns_md(turns: list[dict]) -> str:
    lines = []
    for number, turn in enumerate(turns, start=1):
        lines.append(f"**Turn {number} -- manager:** {turn['question']}\n")
        if "error" in turn:
            lines.append(f"**Agent error:** `{turn['error']}`\n")
            continue
        lines.append(f"**Turn {number} -- agent:** {turn['answer']}\n")
    return "\n".join(lines)


def render(results: dict) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [f"# Agent memory -- evidence\n\nGenerated by `scripts/agent_memory_evidence.py` on {stamp}, "
           "against the real agent, model, Redis and Qdrant (own key prefix, so real memory is untouched).\n"]

    out.append("## 1. Worth remembering vs. not\n\nEach message goes through the agent's self-evaluation "
               "(no memory saved yet). Expected result is in the second column.\n")
    out.append("| Message | Should propose? | Model said | Location / topic / key | Result |\n|---|---|---|---|---|")
    for e in results["examples"]:
        detail = f"{e['location']} / {e['category']} / {e['key']}" if e["remember"] else "-"
        out.append(f"| {e['message']} | {'yes' if e['expected'] else 'no'} | "
                   f"{'propose' if e['remember'] else 'nothing to remember'} | {detail} | {_mark(e['passed'])} |")

    for title, key, approve in (("2. Cycle 1 -- proposal APPROVED and used later", "approved", True),
                                ("3. Cycle 2 -- proposal REJECTED, memory unchanged", "rejected", False)):
        cycle = results[key]
        out.append(f"\n## {title}: {_mark(cycle['passed'])}\n")
        out.append(_turns_md(cycle["turns"]))
        if not approve:
            out.append(f"\nMemory before this cycle held {len(cycle['facts_before'])} fact(s); "
                       f"right after the manager said no it still held {len(cycle['facts_after_decision'])} "
                       f"({'unchanged' if cycle['facts_before'] == cycle['facts_after_decision'] else 'CHANGED'}).\n")
        out.append("\nWhat memory held right after the manager's reply:\n")
        out.append(_fence(cycle["facts_after_decision"]))
        later = cycle["later"]
        out.append(f"**Later, in a NEW conversation -- manager:** {later['question']}\n")
        out.append(f"**Notes the agent was given:** {later.get('notes_used')}\n")
        out.append(f"**Agent:** {later.get('answer') or later.get('error')}\n")

    out.append(f"\n## 4. Forbidden content: {_mark(results['forbidden']['passed'])}\n")
    out.append("A message about staff payroll must never be proposed or saved.\n")
    out.append(f"**Manager:** {results['forbidden']['question']}\n")
    out.append(f"**Agent:** {results['forbidden'].get('answer') or results['forbidden'].get('error')}\n")
    out.append(f"Proposal opened: `{results['forbidden'].get('proposal')}`\n")

    out.append("\n## 5. Audit log (everything above, in order)\n")
    out.append("| When (UTC) | Event | Outcome / reason | Message |\n|---|---|---|---|")
    for entry in results["audit"]:
        message = entry.get("decision_message") or entry.get("origin_message") or entry.get("value") or ""
        outcome = entry.get("outcome") or entry.get("reason") or ""
        out.append(f"| {entry['at'][:19]} | {entry['event']} | {outcome} | {message[:80]} |")
    out.append("\n<details><summary>Full audit entries (JSON)</summary>\n\n" + _fence(results["audit"]) + "\n</details>\n")
    return "\n".join(out)


def main() -> None:
    client = redis.Redis.from_url(memory_redis_url(), decode_responses=True)
    clear_evidence_keys(client)
    store = MemoryStore(client, prefix=EVIDENCE_PREFIX)
    set_store(store)

    results = run_all(store)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render(results), encoding="utf-8")

    print(f"Wrote {OUTPUT_FILE.relative_to(REPO_ROOT)}")
    print(f"  worth-remembering examples: {sum(e['passed'] for e in results['examples'])}/{len(results['examples'])} as expected")
    print(f"  cycle 1 (approved): {_mark(results['approved']['passed'])}")
    print(f"  cycle 2 (rejected): {_mark(results['rejected']['passed'])}")
    print(f"  forbidden content:  {_mark(results['forbidden']['passed'])}")


if __name__ == "__main__":
    main()
