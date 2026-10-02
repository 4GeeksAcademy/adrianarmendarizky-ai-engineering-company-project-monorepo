"""
department_graph.py -- the approval graph for ONE approver (Milestone 9, Part 3).

There is one of these per department that applies, and one for the CEO when the
estimated value is above $50,000 USD a year. Each runs on its OWN thread
("rfp-{ticket_id}:{subject}") with its OWN checkpoint, so one approver waiting
never holds up another. (Tested: in a single shared graph, a department that
asked for changes could not even be revised while another was still waiting.)

    START -> prepare -> await_decision --approve-----------> approve  -> END
                ^             |         \\-reject-----------> reject   -> END
                |             \\-request_changes (within the limit)
                |                          -> revise -> back to prepare
                |                  (over the limit) -> reject_limit -> END
    (an arbiter's forced change enters at force_decision instead of prepare)

await_decision is the human-in-the-loop pause: interrupt() saves the state in
the checkpoint and stops. The only way back in is ApprovalSystem.decide(),
which validates the answer first and then resumes THIS node, not the whole flow.

LangGraph runs a paused node again from its first line on resume, so the code
in front of interrupt() is plain and repeatable: it never writes anything.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import decisions, settings, tracing


class ApprovalState(TypedDict, total=False):
    ticket_id: int
    subject: str            # a department id, or "ceo"
    approver: str           # the owner named in CONTEXT
    metadata: dict          # the RFP details (used by the conflict rules)
    draft_content: str
    evaluation: dict        # a short summary of the draft's EvaluationResult
    card: dict              # extra things the approver should see
    packet: dict            # exactly what the approver is shown
    status: str             # pending / approved / rejected
    decision: dict | None   # the last validated decision
    acted_by: str | None    # who clicked, or the arbiter that forced the change
    estimates: dict         # the numbers the approver gave (cost-vs-feasibility)
    comments: str
    decided_at: str
    revision_count: int
    forced: dict | None     # a change an arbiter forces: {"comments", "by"}
    feedback: str
    rejected_reason: str
    trace: Annotated[list, operator.add]


def build_department_graph(checkpointer, reviser, sink=None):
    """reviser(subject, state) -> {"draft_content", "evaluation", "error"}: how a
    draft is rewritten after a request for changes (in production: Part 2's loop)."""

    @tracing.traced("approval:prepare", sink, input_keys=("revision_count",))
    def prepare(state):
        revision_count = state.get("revision_count", 0)
        packet = {
            "subject": state["subject"],
            "approver": state["approver"],
            "draft_content": state.get("draft_content", ""),
            "evaluation": state.get("evaluation", {}),
            "revision_count": revision_count,
            "revisions_left": max(settings.REVISION_LIMIT - revision_count, 0),
            "card": state.get("card", {}),
        }
        return {"packet": packet, "status": settings.PENDING, "decision": None}

    def await_decision(state):
        # Nothing above this line writes anything: it runs again on every resume.
        answer = interrupt(state["packet"])
        decision = decisions.validate_decision(state["subject"], answer["decision"])
        update = {"decision": decision, "acted_by": answer.get("acted_by"), "comments": decision["comments"]}
        event = tracing.make_event(
            "human:await_decision", state["subject"],
            {"packet_revision": state["packet"]["revision_count"]},
            {"action": decision["action"], "comments": decision["comments"], "estimates": decision["estimates"]},
            actor=update["acted_by"], event_type="human_decision", ticket_id=state.get("ticket_id"))
        tracing.send(sink, event)
        update["trace"] = [event]
        return update

    @tracing.traced("approval:force_decision", sink, input_keys=("forced",))
    def force_decision(state):
        forced = state["forced"]
        decision = {"action": settings.REQUEST_CHANGES, "comments": forced["comments"], "estimates": {}}
        return {"decision": decision, "acted_by": forced["by"], "comments": forced["comments"], "forced": None}

    def route(state):
        action = state["decision"]["action"]
        if action == settings.APPROVE:
            return "approve"
        if action == settings.REJECT:
            return "reject"
        if state.get("revision_count", 0) >= settings.REVISION_LIMIT:
            return "reject_limit"
        return "revise"

    def entry(state):
        return "force_decision" if state.get("forced") else "prepare"

    @tracing.traced("approval:approve", sink, input_keys=("decision",))
    def approve(state):
        return {"status": settings.APPROVED, "estimates": state["decision"]["estimates"],
                "decided_at": tracing.now_iso()}

    @tracing.traced("approval:reject", sink, input_keys=("decision",))
    def reject(state):
        return {"status": settings.REJECTED, "decided_at": tracing.now_iso(),
                "rejected_reason": state["decision"]["comments"]}

    @tracing.traced("approval:reject_limit", sink, input_keys=("revision_count",))
    def reject_limit(state):
        return {"status": settings.REJECTED, "decided_at": tracing.now_iso(),
                "rejected_reason": (f"Changes were requested more than {settings.REVISION_LIMIT} times, "
                                    f"so the section is rejected and needs a person to restart it.")}

    @tracing.traced("approval:revise", sink, input_keys=("revision_count", "feedback"))
    def revise(state):
        decision = state["decision"]
        who = state.get("acted_by") or state["approver"]
        feedback = f"Requested by {who}: {decision['comments']}"
        result = reviser(state["subject"], {**state, "feedback": feedback})
        return {
            "draft_content": result["draft_content"],
            "evaluation": result["evaluation"],
            "revision_count": state.get("revision_count", 0) + 1,
            "estimates": {},          # the numbers belonged to the old draft
            "status": settings.PENDING,
            "feedback": feedback,
        }

    builder = StateGraph(ApprovalState)
    builder.add_node("prepare", prepare)
    builder.add_node("await_decision", await_decision)
    builder.add_node("force_decision", force_decision)
    builder.add_node("approve", approve)
    builder.add_node("reject", reject)
    builder.add_node("reject_limit", reject_limit)
    builder.add_node("revise", revise)

    builder.add_conditional_edges(START, entry, {"force_decision": "force_decision", "prepare": "prepare"})
    builder.add_edge("prepare", "await_decision")
    for source in ("await_decision", "force_decision"):
        builder.add_conditional_edges(
            source, route,
            {"approve": "approve", "reject": "reject", "reject_limit": "reject_limit", "revise": "revise"})
    builder.add_edge("revise", "prepare")
    builder.add_edge("approve", END)
    builder.add_edge("reject", END)
    builder.add_edge("reject_limit", END)
    return builder.compile(checkpointer=checkpointer)
