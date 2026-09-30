"""
services/api/agent/guard_nodes.py -- Milestone 8 Part 2 (SEC-114): the two
graph steps that wrap the protection harness around the model.

    guard_input_node    the input guard. Classifies the RAW message
                        BEFORE it reaches memory, tool routing, or any
                        model call, using guardrails/patterns.py's
                        deterministic classify_input(). A blocked scope
                        gets its canned answer right here and skips
                        every later node, including Part 1's memory
                        self-evaluation -- a message flagged as a
                        jailbreak attempt or an off-domain task is never
                        fed to another LLM call as "worth remembering?"
                        input. That closes a real gap Part 1 had: its
                        self_evaluate call used to receive ANY raw user
                        text, including adversarial text, with nothing
                        upstream filtering it first.
    output_guard_node   the LAST node on every path through the graph,
                        blocked or not. Scans the final answer with
                        guardrails/patterns.py's check_output() and
                        replaces it if that finds a leaked system prompt
                        or the same sensitive-content patterns Part 1
                        already blocks from memory.

Why classification here is pure code, never a model call: see
guardrails/patterns.py's module docstring. That also means these two
nodes need no live LLM to unit-test -- see
tests/pipelines/test_agent_guardrails.py.
"""

from .guardrails import messages, patterns, telemetry
from .state import AgentState


def guard_input_node(state: AgentState) -> dict:
    question = state["question"]
    scope = patterns.classify_input(question)
    if scope == "domain":
        return {"guard_scope": scope}

    language = patterns.guess_language(question)
    category = "security" if scope == "instruction_change" else "content"
    telemetry.log_event(category, scope, question=question[:500])
    return {"guard_scope": scope, "answer": messages.say(scope, language)}


def route_after_guard(state: AgentState) -> str:
    return "check_pending" if state.get("guard_scope") == "domain" else "output_guard"


def output_guard_node(state: AgentState) -> dict:
    answer = state.get("answer")
    reasons = patterns.check_output(answer)
    if not reasons:
        return {}
    for reason in reasons:
        category = "structural" if reason == "empty_answer" else "content"
        telemetry.log_event(category, reason)
    language = patterns.guess_language(state["question"])
    return {"answer": messages.say("output_blocked", language)}
