"""
services/api/agent/memory_nodes.py -- the three graph steps that add memory
(Milestone 8, Part 1). Still ONE agent and ONE graph; these are just extra
steps around the existing ones:

    receive_question -> check_pending -> load_memory -> (tools / RAG) -> generate -> self_evaluate

  check_pending  If this conversation has an open memory proposal, the manager's
                 new message is judged FIRST: approve, reject, edit, or unclear.
                 Approved -> saved. Rejected/unclear/expired -> dropped. Every
                 outcome is written to the audit log. If the message also
                 contains another question, that question continues through the
                 graph as normal; if it was only a yes/no, the graph skips
                 straight to the end.
  load_memory    Looks up saved facts for the location(s) the question mentions
                 and hands them to generate as "manager notes".
  self_evaluate  After the answer is ready, asks: is there something new or
                 corrected here worth remembering? If so, it opens ONE
                 proposal and adds the "do you want me to remember this?"
                 question to the end of the same answer. Nothing is written yet.

Memory only works when the request carries a user_id and a session_id (the
HTTP route sets them for managers and admins). Calls without them -- like the
older agent evals -- skip all of this and behave exactly as before.

If Redis or the model is unavailable, these steps log the problem and let the
agent answer normally: memory is an extra, never a reason for the agent to fail.
"""

import logging

from redis.exceptions import RedisError

from .memory import llm_steps, policy
from .memory.messages import say
from .memory.store import format_notes, get_store
from .state import AgentState

logger = logging.getLogger(__name__)

# Messages shorter than this ("thanks", "ok") can't hold a correction, so the
# self-evaluation model call is skipped entirely.
MIN_CHARS_TO_EVALUATE = 15


def _memory_enabled(state: AgentState) -> bool:
    return bool(state.get("user_id") and state.get("session_id"))


def check_pending_node(state: AgentState) -> dict:
    result = {"memory_ack": None, "memory_handled": False, "skip_rest": False}
    if not _memory_enabled(state):
        return result

    session_id, user_id, message = state["session_id"], state["user_id"], state["question"]
    try:
        store = get_store()
        pending = store.get_pending(session_id, user_id)
        if pending is None:
            return result

        decision = llm_steps.classify_decision(pending, message)
        lang = decision.language
        location, fact = pending["location"], pending["fact"]
        result["memory_handled"] = True

        if decision.label == "approve":
            saved = store.write_fact(pending, decision_message=message)
            if saved["status"] == "written":
                store.resolve_pending(session_id, pending, "approved", decision_message=message)
                result["memory_ack"] = say("saved", lang, fact=fact, location=location)
            else:
                store.resolve_pending(session_id, pending, "discarded_write_refused",
                                      decision_message=message, detail=saved["reason"])
                result["memory_ack"] = say("rate_limited" if saved["reason"] == "rate_limited" else "not_saved", lang)

        elif decision.label == "reject":
            store.resolve_pending(session_id, pending, "rejected", decision_message=message)
            result["memory_ack"] = say("rejected", lang)

        elif decision.label == "edit":
            clean, why = policy.validate_proposal({**pending, "fact": decision.edited_fact})
            if clean is None:
                store.resolve_pending(session_id, pending, "discarded_policy",
                                      decision_message=message, detail=why)
                result["memory_ack"] = say("edit_refused", lang)
            else:
                # Still the same single open proposal, now with the corrected wording.
                store.edit_pending(session_id, pending, clean["fact"], decision_message=message)
                result["memory_ack"] = say("edited", lang, fact=clean["fact"], location=location)

        else:  # unclear: never assume yes. Drop the proposal and carry on.
            store.resolve_pending(session_id, pending, "discarded_unclear", decision_message=message)
            result["memory_ack"] = say("discarded_unclear", lang)
            return result  # the message is treated as a normal question

        # approve / reject / edit: if the message held another request, answer it.
        if decision.remaining_request:
            result["question"] = decision.remaining_request
        else:
            result["skip_rest"] = True
        return result

    except RedisError:
        logger.exception("agent memory unavailable during check_pending")
        return {"memory_ack": None, "memory_handled": False, "skip_rest": False}


def route_after_decision(state: AgentState) -> str:
    return "self_evaluate" if state.get("skip_rest") else "load_memory"


def load_memory_node(state: AgentState) -> dict:
    if not _memory_enabled(state):
        return {"memory_notes": None}
    try:
        notes = format_notes(get_store().relevant_facts(state["question"]))
    except RedisError:
        logger.exception("agent memory unavailable during load_memory")
        return {"memory_notes": None}
    return {"memory_notes": notes or None}


def self_evaluate_node(state: AgentState) -> dict:
    """Last step of every run: puts together the final answer (any memory
    message + the answer + a new proposal question, if there is one)."""
    proposal = None
    proposal_text = None

    can_propose = (_memory_enabled(state) and not state.get("memory_handled")
                   and len(state["question"].strip()) >= MIN_CHARS_TO_EVALUATE)
    if can_propose:
        try:
            proposal, proposal_text = _maybe_open_proposal(state)
        except RedisError:
            logger.exception("agent memory unavailable during self_evaluate")
        except Exception:
            logger.exception("memory self-evaluation failed; answering without a proposal")

    parts = [state.get("memory_ack"), state.get("answer"), proposal_text]
    return {"answer": "\n\n".join(p for p in parts if p), "memory_proposal": proposal}


def _maybe_open_proposal(state: AgentState) -> tuple[dict | None, str | None]:
    store = get_store()
    message = state["question"]
    evaluation = llm_steps.evaluate_message(message, store.all_facts())
    if not evaluation.remember:
        return None, None

    clean, why = policy.validate_proposal(evaluation.model_dump())
    if clean is None:
        # Blocked by the code rules (e.g. payroll). Logged, never proposed.
        store.log("proposal_blocked", user_id=state["user_id"], session_id=state["session_id"],
                  reason=why, origin_message=message[:1000])
        return None, None

    proposal = store.create_pending(
        session_id=state["session_id"], user_id=state["user_id"], fields=clean,
        reason=evaluation.reason, language=evaluation.language, origin_message=message,
    )
    if proposal is None:  # one is already open: never a second
        return None, None

    text = say("ask", evaluation.language, location=clean["location"], fact=clean["fact"])
    if proposal["replaces"]:
        text += say("ask_replaces", evaluation.language, old=proposal["replaces"])
    return proposal, text
