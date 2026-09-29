"""services/api/agent/guardrails/ -- the protection harness (Milestone 8,
Part 2 / ticket SEC-114): everything that wraps the model so the agent
can't be turned into a general-purpose assistant or manipulated by text
it reads.

    patterns.py       deterministic, code-only detectors: the input guard
                       (classify_input), the isolation layer
                       (sanitize_external_content / sanitize_chunks /
                       sanitize_notes), and the output guard (check_output)
    messages.py        the fixed English/Spanish replies for each blocked
                       scope
    telemetry.py       logs every guardrail trigger (structural, content,
                       or security) and exposes a count summary

The graph nodes that use these live in agent/guard_nodes.py. The system
prompt these back up lives in data/pipelines/rag.py (SYSTEM_PROMPT) --
see that file's module docstring for why it stays there rather than here.
"""
