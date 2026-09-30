# Agent Memory — Design (Milestone 8, Part 1)

The Brasaland manager-support agent used to start every conversation from zero. Location managers had to repeat the same corrections ("the Medellín meat supplier delivers on Tuesdays") week after week. Now the agent can **propose** remembering a correction, the manager **approves or rejects** it, and only approved facts are saved and used in later conversations.

It is still one agent and one graph. Memory adds three steps around the existing ones:

```
receive_question -> check_pending -> load_memory -> (tools / RAG) -> generate -> self_evaluate -> END
```

| Step | What it does | Code |
|---|---|---|
| `check_pending` | If a proposal is open, decides whether the manager's new message approves, rejects, edits it, or is unclear. Saves or drops it. | `services/api/agent/memory_nodes.py` |
| `load_memory` | Finds saved facts for the locations the question mentions and gives them to the answer step as "manager notes". | `services/api/agent/memory_nodes.py` |
| `self_evaluate` | After the answer is ready, asks "is anything here worth remembering?". If yes, opens **one** proposal and adds the question to the end of the same answer. Nothing is saved yet. | `services/api/agent/memory_nodes.py` |

If the message is only a "yes" or "no", `check_pending` skips straight to the end (there is nothing else to look up). If it also contains another question, that question is answered normally.

## Why Redis (and not a vector database or a graph)

What the agent needs to remember is small and simple: short facts about one location, like opening hours or a delivery day. It always looks them up by **location and topic**, never by "meaning". So:

- **Redis (chosen).** Already in the project from DEV-55. Fast, easy to read and to test. Each fact has a key like `agent_memory:fact:medellin:suppliers:meat_delivery_days`, so a new value for the same topic **replaces** the old one instead of piling up. It uses its own database (db 1, not Celery's db 0), and the Redis container now keeps its data in a volume (`docker-compose.yml`), so memory survives restarts.
- **Vector database (ruled out).** Good for searching long documents by meaning. We look facts up by name, and mixing memory into Qdrant would risk polluting the read-only company knowledge base (`brasaland_knowledge`). Memory never touches Qdrant.
- **Knowledge graph (ruled out).** Useful when facts have relationships to follow (this depends on that). Here they don't.
- **Fine-tuning (ruled out).** Slow, expensive, hard to update, and it can't "forget" one wrong fact.
- **Conversation history / prompt caching.** Only lasts one conversation; the problem is remembering *between* conversations.

## What is worth remembering

Only four topics are allowed: `hours`, `suppliers`, `known_incidents`, `communication_prefs`. It must be new or corrected, about a specific location, and a repeatable pattern (still true next week).

**Should generate a proposal** (examples from the CONTEXT file):
1. "Actually the vegetable supplier in Medellín delivers on Wednesdays, not Tuesdays like you said before."
2. "The Miami Beach location now closes at 11pm on weekends, that changed last month."
3. "That zero-sales alert at location 7 was because of a power outage, not a POS error. It's happened twice this month."

**Should NOT generate a proposal** (the agent dismisses these as "nothing to remember"):
1. "What was yesterday's average ticket in Bogotá?" (one-off question; the data lives elsewhere)
2. "Thanks, that answers my question." (nothing new)
3. "Can you translate this into English for Ashley's report?" (single-use task)

Messages under 15 characters ("thanks!") skip the check completely, with no model call.

## How a proposal is confirmed (and logged)

- The proposal is a question at the end of the agent's normal answer: *"Do you want me to remember this for next time? Medellin: …"* (in English or Spanish, matching the manager).
- The manager's next message is classified into a label — `approve`, `reject`, `edit` or `unclear` — by a model call that must return a label, plus how confident it is. It is **not** a `"yes" in message` check. Anything that isn't a confident label counts as `unclear`.
- **Only approve saves.** `reject`, `unclear`, and an expired proposal are all dropped. `edit` changes the wording and asks again.
- **Only one proposal can be open at a time.** While one is open, no second one is created. The store itself also refuses (`SET ... NX`), so two fast requests can't sneak in two.
- **Silence or a change of topic = no.** If the manager asks about something else, the proposal is dropped and that message is answered normally. An unanswered proposal also expires after 10 minutes.
- **After a decision** the conversation continues normally, including when the same message also asks another question. (The agent won't open a *new* proposal in the same turn it closes one, to keep it simple and avoid asking twice.)
- **Audit log.** Every step is written to an append-only list in Redis: proposal created (with the message that caused it), edited, resolved (approved / rejected / discarded_unclear / discarded_expired / discarded_policy), fact saved, blocked by policy, refused, expired, evicted. Rejected proposals are logged too. Read it at `GET /agent/memory/audit` (admins only). The code has no method that edits or deletes an audit entry.

## Design decisions

**1. What kind of memory does the company need, and why not the others?**
Simple key-value facts per location (a light form of "semantic" memory), stored in Redis. Not vector search, graph, or fine-tuning: see the section above.

**2. What must never enter memory, no matter who asks?**
From CONTEXT: Brasa Points customer personal data, payroll and staff compensation, and anything one-off. These are checked **in code**, not just in the prompt (`services/api/agent/memory/policy.py`): payroll and salary words (English and Spanish), emails, phone numbers, customer ids, ID-document words, and loyalty-account details are blocked. The check runs when a proposal is created, when it is edited, and again inside `write_fact()` right before saving, so nothing can skip it. The one-off rule can't be checked with code, so the model judges it using the "repeatable" test in its instructions; the audit log records what was proposed so it can be reviewed.

**3. How does the agent decide what to forget, and what happens if the manager never responds?**
- Unanswered proposal: dropped after 10 minutes (logged as `discarded_expired`).
- Known incident not seen again for 90 days: forgotten. (Incidents go stale quickly. If it happens again it is counted, not duplicated.)
- Hours, suppliers and preferences: kept, but after 180 days without being re-confirmed they are labelled "may be outdated" when the agent uses them. (Wrong opening hours are worse than none, but deleting them would lose good facts.)
- Hard cap of 40 facts per location: incidents go first, then outdated facts, then the least recently confirmed.
- A new value for the same topic replaces the old one; only the last 3 old values are kept.
- The cleanup runs automatically after every save, and for everything with `scripts/agent_memory_consolidate.py` (cron-friendly).

**4. How is a malicious user stopped from poisoning memory with false "corrections"?**
Several layers, so no single one has to be perfect:
- Login is required, and only managers and admins can use memory. Every fact records who approved it.
- Nothing is saved without an explicit, classified approval, and what is saved is the exact proposal the manager saw, never text from the approving message.
- If a new fact would replace an existing one, the question says so ("This would replace what I have now: …").
- Instruction-like text ("ignore previous instructions…") and odd characters are blocked in code. Saved notes are shown to the model as labelled notes, "never instructions".
- A limit of 10 saved facts per person per day.
- Everything is in the audit log. If something wrong gets in, you can see who approved it and when.
- Saved notes never override live data from tools (tickets, inventory).

**5. Why doesn't this need a multi-agent design?**
Self-evaluation is one extra model call in the same graph, and the "did they approve?" check is one small classification step. Both are just steps in one agent's flow, sharing the same state. A second agent would add coordination work without adding any ability the extra steps don't already give.
(One honest difference from the ticket's "one call" suggestion: many of this agent's answers don't come from the model at all — ticket and inventory answers are formatted directly — so there isn't always an answer call to attach the `memory_proposal` field to. The self-evaluation is therefore its own small call, still inside the same agent.)

## Known limits

- The agent only loads notes when the question names a location (by name or id like `COL-07`). It doesn't yet know which restaurant the logged-in manager runs.
- A place not on the 14-location list (e.g. "Miami Beach", used in the CONTEXT examples) is accepted as a label; the fact still needs approval and passes every other check.
- The audit log is append-only *in the code*. Someone with direct access to Redis could still change it; a real production system would ship it to write-once storage.
- Whether a message is "worth remembering" is a model judgment and won't always be right; that's why nothing is saved without the manager's approval.

## Running and testing

```bash
# once: test-only dependency
cd services/api && uv add --dev fakeredis

# tests (no Qdrant, model or Redis server needed)
uv run python -m pytest ../../tests/pipelines/test_agent_memory.py -v

# evidence with the real model, Redis and Qdrant running -> writes docs/agent-memory/evidence.md
uv run python ../../scripts/agent_memory_evidence.py

# cleanup for everything
uv run python ../../scripts/agent_memory_consolidate.py
```

How to try it by hand: log in as a user with the `manager` role, `POST /agent/query` with a correction, then send your reply with the same `session_id` from the first response.
