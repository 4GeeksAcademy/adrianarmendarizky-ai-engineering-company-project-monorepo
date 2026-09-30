"""services/api/agent/memory/ -- the agent's long-term memory (Milestone 8, Part 1).

    policy.py     what may (and may never) be remembered, and the timing numbers
    store.py      the Redis-backed store: facts, the one pending proposal, audit log
    llm_steps.py  the two small model calls: "is this worth remembering?" and
                  "did the user approve / reject / edit the pending proposal?"
    messages.py   the fixed English/Spanish sentences the agent adds to its answers

The graph nodes that use these live in agent/memory_nodes.py.
"""
