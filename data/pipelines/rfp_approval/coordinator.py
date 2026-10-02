"""
coordinator.py -- the ticket-level graph with the ARBITRATION node
(Milestone 9, Part 3).

    START -> detect -> (any conflict?) -> arbitrate -> END
                             no ----------------------> END

detect finds the CONTEXT section 7 conflicts from structured data
(conflicts.py). arbitrate is the dedicated arbitration node: it settles each
conflict the way CONTEXT says, with the FIXED arbiter, never by agents
agreeing among themselves and never by a model:

  setup-sla-breach     rule: Felipe Guerrero rejects (Camila Ospina escalates when other
                       departments still embed it). Every breaching section is forced to
                       request_changes. No human choice is needed.
  cost-vs-feasibility  a NAMED HUMAN decides: Camila Ospina chooses raise_price or
                       reduce_scope (interrupt). Both sections are then forced to
                       request_changes. This is the only pause in this graph.
  ceo-threshold        rule: the final document stays blocked until the CEO approves.
                       (The CEO's own approval is a separate graph; see system.py.)

The node only DECIDES. Carrying out the forced changes is done by
ApprovalSystem, one department at a time, on that department's own thread.
Everything before interrupt() is plain and repeatable.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import conflicts as conflict_rules
from . import decisions, settings, tracing


class CoordinatorState(TypedDict, total=False):
    ticket_id: int
    subject: str  # always "coordinator" (the trace reads it)
    metadata: dict
    sections: dict
    ceo_status: str
    conflicts: list
    warnings: list
    resolutions: list
    forced_changes: dict  # department_id -> {"comments", "by"}
    trace: Annotated[list, operator.add]


def _evidence(conflict: dict) -> str:
    evidence = conflict["details"].get("evidence", {})
    first = next(iter(evidence.values()), [""])
    return first[0] if first else ""


def build_coordinator_graph(checkpointer, sink=None):

    @tracing.traced("approval:detect_conflicts", sink, input_keys=("ceo_status",))
    def detect(state):
        result = conflict_rules.detect_conflicts(
            state.get("metadata", {}), state.get("sections", {}), state.get("ceo_status", settings.PENDING))
        return {
            "conflicts": result["conflicts"], "warnings": result["warnings"],
            "resolutions": [], "forced_changes": {},   # a fresh run starts with nothing decided
        }

    def arbitrate(state):
        resolutions, forced = [], {}

        def force(department_id: str, comments: str, by: str) -> None:
            entry = forced.setdefault(department_id, {"comments": [], "by": by})
            entry["comments"].append(comments)

        for conflict in state["conflicts"]:
            trigger = conflict["trigger"]
            decided_by = conflict["escalated_to"] or conflict["arbiter"]

            if trigger == settings.TRIGGER_SETUP:
                minimum = conflict["details"]["minimum_business_days"]
                message = (f"Arbitration {trigger} (arbiter: {decided_by}): a draft promises setup or delivery in "
                           f"fewer than {minimum} business days. Promise at least {minimum}. "
                           f"Text: \"{_evidence(conflict)}\"")
                for department_id in conflict["sections"]:
                    force(department_id, message, decided_by)
                resolutions.append({"trigger": trigger, "arbiter": conflict["arbiter"], "decided_by": decided_by,
                                    "rule": conflict["resolution"], "forced_sections": conflict["sections"]})

            elif trigger == settings.TRIGGER_COST:
                answer = interrupt({                      # the named arbiter decides: a real pause
                    "trigger": trigger, "arbiter": conflict["arbiter"],
                    "choices": list(settings.ARBITRATION_CHOICES[trigger]),
                    "details": conflict["details"], "sections": conflict["sections"],
                })
                choice = decisions.validate_arbitration(trigger, answer["response"])
                details = conflict["details"]
                what = "Raise the price" if choice["choice"] == settings.RAISE_PRICE else "Reduce the scope"
                message = (f"Arbitration {trigger} (arbiter: {decided_by}): {what}. {choice['comments']} "
                           f"(ingredient cost per cover ${details['ingredient_cost_per_cover_usd']:g} is above the "
                           f"price per cover ${details['price_per_cover_usd']:g}).")
                for department_id in conflict["sections"]:
                    force(department_id, message, decided_by)
                resolutions.append({"trigger": trigger, "arbiter": conflict["arbiter"], "decided_by": decided_by,
                                    "choice": choice["choice"], "comments": choice["comments"],
                                    "acted_by": answer.get("acted_by"), "forced_sections": conflict["sections"]})

            elif trigger == settings.TRIGGER_CEO:
                resolutions.append({"trigger": trigger, "arbiter": conflict["arbiter"], "decided_by": decided_by,
                                    "rule": conflict["resolution"],
                                    "ceo_status": conflict["details"]["ceo_status"]})

        forced_changes = {d: {"comments": " ".join(v["comments"]), "by": v["by"]} for d, v in forced.items()}
        update = {"resolutions": resolutions, "forced_changes": forced_changes}
        event = tracing.make_event(
            "approval:arbitrate", state.get("subject"),
            {"conflicts": [c["trigger"] for c in state["conflicts"]]},
            {"resolutions": resolutions, "forced_changes": sorted(forced_changes)},
            event_type="arbitration")
        tracing.send(sink, event)
        update["trace"] = [event]
        return update

    def after_detect(state):
        return "arbitrate" if state.get("conflicts") else END

    builder = StateGraph(CoordinatorState)
    builder.add_node("detect", detect)
    builder.add_node("arbitrate", arbitrate)
    builder.add_edge(START, "detect")
    builder.add_conditional_edges("detect", after_detect, {"arbitrate": "arbitrate", END: END})
    builder.add_edge("arbitrate", END)
    return builder.compile(checkpointer=checkpointer)
