"""
system.py -- the one door into the approval workflow (Milestone 9, Part 3).

ApprovalSystem owns the graphs and is the ONLY way to start, resume or finish
an approval. Everything the API and the end-to-end script do goes through its
methods, so the rules below are enforced in one place:

  open_ticket(...)         starts one approval graph per department; each one runs to its
                           interrupt() and waits
  decide(...)              a human answers: validated FIRST, then that ONE department's
                           graph is resumed from its pause (never restarted, never
                           another department's), then the ticket is coordinated
  answer_arbitration(...)  the named arbiter answers a cost-vs-feasibility conflict
  continue_subject(...)    picks a graph up from its last checkpoint after a crash
  coordinate(...)          conflicts -> arbitration node -> forced changes -> CEO ->
                           final document, once EVERYTHING required is approved
  reset_ticket(...)        forgets a ticket's checkpoints (a fresh start)

Thread ids are namespaced by ticket and approver ("rfp-12:operaciones",
"rfp-12:ceo", "rfp-12:coordinator"), so concurrent tickets and departments
never share a checkpoint.

State of every approval lives in the checkpoint, not in this object. A new
ApprovalSystem on the same checkpoint file sees exactly what the old one did,
which is what makes a restart harmless.
"""

import threading
from collections import defaultdict

from langgraph.types import Command

from rfp_intake.state import DEPARTMENT_IDS

from . import conflicts as conflict_rules
from . import decisions, final_document, settings, tracing
from .coordinator import build_coordinator_graph
from .department_graph import build_department_graph

COORDINATOR = "coordinator"


class ApprovalError(Exception):
    """Base class for the workflow's own refusals."""


class AlreadyOpen(ApprovalError):
    """This ticket already has approvals in progress."""


class UnknownTicket(ApprovalError):
    """No approval has been opened for this ticket (or this approver)."""


class NotWaiting(ApprovalError):
    """That approver is not waiting for a decision right now."""


def thread_id(ticket_id: int, subject: str) -> str:
    return f"rfp-{ticket_id}:{subject}"


class ApprovalSystem:
    def __init__(self, checkpointer, reviser, sink=None):
        self.checkpointer = checkpointer
        self.sink = sink
        self.departments = build_department_graph(checkpointer, reviser, sink)
        self.coordinator = build_coordinator_graph(checkpointer, sink)
        self._locks = defaultdict(threading.RLock)
        self._guard = threading.Lock()

    # --- small helpers -----------------------------------------------------

    def _lock(self, ticket_id: int):
        with self._guard:
            return self._locks[ticket_id]

    @staticmethod
    def _config(ticket_id: int, subject: str) -> dict:
        return {"configurable": {"thread_id": thread_id(ticket_id, subject)}}

    def subject_state(self, ticket_id: int, subject: str):
        """What one approver's checkpoint says, or None if it was never opened."""
        snapshot = self.departments.get_state(self._config(ticket_id, subject))
        if not snapshot.values:
            return None
        return {"values": snapshot.values, "waiting": snapshot.next == ("await_decision",), "next": snapshot.next}

    def snapshot(self, ticket_id: int) -> dict:
        """The whole ticket as the conflict rules and the final document see it."""
        sections, metadata = {}, {}
        for department_id in DEPARTMENT_IDS:
            state = self.subject_state(ticket_id, department_id)
            if state is None:
                continue
            values = state["values"]
            metadata = metadata or values.get("metadata", {})
            sections[department_id] = {
                "draft_content": values.get("draft_content", ""),
                "status": values.get("status", settings.PENDING),
                "estimates": values.get("estimates") or {},
                "approver": values.get("approver"),
                "acted_by": values.get("acted_by"),
                "decided_at": values.get("decided_at"),
                "comments": values.get("comments", ""),
                "revision_count": values.get("revision_count", 0),
                "rejected_reason": values.get("rejected_reason"),
                "waiting": state["waiting"],
            }
        ceo = self.subject_state(ticket_id, settings.CEO_SUBJECT)
        return {
            "metadata": metadata,
            "sections": sections,
            "ceo": None if ceo is None else {**ceo["values"], "waiting": ceo["waiting"]},
        }

    def _event(self, ticket_id, agent, event_type, output, subject=None, actor=None):
        tracing.send(self.sink, tracing.make_event(agent, subject, {"ticket_id": ticket_id}, output,
                                                   actor=actor, event_type=event_type, ticket_id=ticket_id))

    def describe(self, ticket_id: int) -> dict:
        """Everything a screen needs to show one ticket's approvals. Read-only:
        it changes nothing and writes no trace events."""
        snapshot = self.snapshot(ticket_id)
        if not snapshot["sections"]:
            raise UnknownTicket(f"No approval is open for ticket {ticket_id}.")
        ceo_status = (snapshot["ceo"] or {}).get("status", settings.PENDING)
        found = conflict_rules.detect_conflicts(snapshot["metadata"], snapshot["sections"], ceo_status)

        paused = self.coordinator.get_state(self._config(ticket_id, COORDINATOR))
        arbitration = None
        if paused.values and paused.next == ("arbitrate",):
            arbitration = paused.tasks[0].interrupts[0].value

        approvers = []
        for subject in [*DEPARTMENT_IDS, settings.CEO_SUBJECT]:
            state = self.subject_state(ticket_id, subject)
            if state is None:
                continue
            values = state["values"]
            packet = values.get("packet") or {}
            approvers.append({
                "subject": subject,
                "approver": values.get("approver"),
                "status": values.get("status", settings.PENDING),
                "waiting": state["waiting"],
                "acted_by": values.get("acted_by"),
                "comments": values.get("comments", ""),
                "estimates": values.get("estimates") or {},
                "decided_at": values.get("decided_at"),
                "rejected_reason": values.get("rejected_reason"),
                "revision_count": values.get("revision_count", 0),
                "revisions_left": max(settings.REVISION_LIMIT - values.get("revision_count", 0), 0),
                "draft_content": values.get("draft_content", ""),
                "evaluation": values.get("evaluation", {}),
                "card": packet.get("card") or values.get("card", {}),
            })
        return {"approvers": approvers, "arbitration": arbitration,
                "conflicts": found["conflicts"], "warnings": found["warnings"]}

    # --- starting and finishing ----------------------------------------------

    def open_ticket(self, ticket_id: int, metadata: dict, sections: dict) -> dict:
        """sections: department_id -> {"draft_content", "evaluation", "card"}"""
        with self._lock(ticket_id):
            for department_id in sections:
                if self.subject_state(ticket_id, department_id) is not None:
                    raise AlreadyOpen(f"Ticket {ticket_id} already has an approval open for {department_id}.")
            for department_id in DEPARTMENT_IDS:
                if department_id not in sections:
                    continue
                section = sections[department_id]
                self.departments.invoke({
                    "ticket_id": ticket_id, "subject": department_id,
                    "approver": settings.APPROVERS[department_id], "metadata": metadata,
                    "draft_content": section["draft_content"], "evaluation": section.get("evaluation", {}),
                    "card": section.get("card", {}), "revision_count": 0, "status": settings.PENDING,
                    "estimates": {},
                }, self._config(ticket_id, department_id))
            self._event(ticket_id, "approval:open_ticket", "ticket_opened",
                        {"departments": [d for d in DEPARTMENT_IDS if d in sections]})
            return self.coordinate(ticket_id)

    def reset_ticket(self, ticket_id: int) -> None:
        """Forget every checkpoint of this ticket, so it can be opened again."""
        with self._lock(ticket_id):
            for subject in (*DEPARTMENT_IDS, settings.CEO_SUBJECT, COORDINATOR):
                self.checkpointer.delete_thread(thread_id(ticket_id, subject))
            self._event(ticket_id, "approval:reset_ticket", "ticket_reset", {})

    # --- the human answers -----------------------------------------------------

    def decide(self, ticket_id: int, subject: str, response, acted_by: str) -> dict:
        with self._lock(ticket_id):
            decision = decisions.validate_decision(subject, response)   # refused here, before the graph sees it
            state = self.subject_state(ticket_id, subject)
            if state is None:
                raise UnknownTicket(f"No approval is open for {subject} on ticket {ticket_id}.")
            if not state["waiting"]:
                status = state["values"].get("status")
                raise NotWaiting(f"{subject} is not waiting for a decision (status: {status}).")
            self.departments.invoke(
                Command(resume={"decision": decision, "acted_by": acted_by}), self._config(ticket_id, subject))
            return self.coordinate(ticket_id)

    def answer_arbitration(self, ticket_id: int, trigger: str, response, acted_by: str) -> dict:
        with self._lock(ticket_id):
            answer = decisions.validate_arbitration(trigger, response)
            config = self._config(ticket_id, COORDINATOR)
            snapshot = self.coordinator.get_state(config)
            if not snapshot.values or snapshot.next != ("arbitrate",):
                raise NotWaiting("No arbitration is waiting for an answer on this ticket.")
            pending = snapshot.tasks[0].interrupts[0].value
            if pending["trigger"] != trigger:
                raise NotWaiting(f"The waiting arbitration is '{pending['trigger']}', not '{trigger}'.")
            result = self.coordinator.invoke(Command(resume={"response": answer, "acted_by": acted_by}), config)
            return self._after_coordinator(ticket_id, result)

    def continue_subject(self, ticket_id: int, subject: str) -> dict:
        """After a crash in the middle of a step: carry on from the last checkpoint."""
        with self._lock(ticket_id):
            state = self.subject_state(ticket_id, subject)
            if state is None:
                raise UnknownTicket(f"No approval is open for {subject} on ticket {ticket_id}.")
            if state["next"]:
                self.departments.invoke(None, self._config(ticket_id, subject))
            return self.coordinate(ticket_id)

    # --- coordination ------------------------------------------------------------

    def coordinate(self, ticket_id: int) -> dict:
        with self._lock(ticket_id):
            snapshot = self.snapshot(ticket_id)
            if not snapshot["sections"]:
                raise UnknownTicket(f"No approval is open for ticket {ticket_id}.")

            config = self._config(ticket_id, COORDINATOR)
            paused = self.coordinator.get_state(config)
            if paused.values and paused.next == ("arbitrate",):
                # An arbiter has not answered yet: nothing new is decided until she does.
                return self._outcome(ticket_id, "arbitration_pending", snapshot,
                                     arbitration=paused.tasks[0].interrupts[0].value)

            result = self.coordinator.invoke({
                "ticket_id": ticket_id, "subject": COORDINATOR, "metadata": snapshot["metadata"],
                "sections": snapshot["sections"],
                "ceo_status": (snapshot["ceo"] or {}).get("status", settings.PENDING),
            }, config)
            return self._after_coordinator(ticket_id, result)

    def _after_coordinator(self, ticket_id: int, result: dict) -> dict:
        interrupts = result.get("__interrupt__")
        if interrupts:
            return self._outcome(ticket_id, "arbitration_pending", self.snapshot(ticket_id),
                                 arbitration=interrupts[0].value, result=result)

        forced = result.get("forced_changes") or {}
        if forced:
            for subject, change in forced.items():
                self._force_changes(ticket_id, subject, change["comments"], change["by"])
            snapshot = self.snapshot(ticket_id)
            # A forced change counts as a revision, so it can push a section over the limit.
            rejected = [d for d, s in snapshot["sections"].items() if s["status"] == settings.REJECTED]
            if rejected:
                return self._outcome(ticket_id, "department_rejected", snapshot, result=result,
                                     forced=forced, rejected=rejected)
            return self._outcome(ticket_id, "changes_forced", snapshot, result=result, forced=forced)

        return self._progress(ticket_id, result)

    def _force_changes(self, ticket_id: int, subject: str, comments: str, by: str) -> None:
        """An arbiter's rule sends a section back for changes."""
        state = self.subject_state(ticket_id, subject)
        if state is None or state["values"].get("status") == settings.REJECTED:
            return
        actor = f"arbiter: {by}"
        config = self._config(ticket_id, subject)
        if state["waiting"]:
            # Its owner has not answered yet: the arbiter's rule answers for the owner.
            decision = decisions.validate_decision(
                subject, {"action": settings.REQUEST_CHANGES, "comments": comments})
            self.departments.invoke(Command(resume={"decision": decision, "acted_by": actor}), config)
        else:
            # Already approved: re-open it.
            self.departments.invoke({"forced": {"comments": comments, "by": actor}}, config)

    def _open_ceo(self, ticket_id: int, snapshot: dict) -> None:
        value = conflict_rules.estimated_annual_value_usd(snapshot["metadata"])
        card = {
            "estimated_annual_value_usd": value,
            "threshold_usd": settings.CEO_APPROVAL_THRESHOLD_USD,
            "approved_sections": [
                {"department_id": d, "approver": s["approver"], "approved_at": s["decided_at"]}
                for d, s in snapshot["sections"].items()],
        }
        self.departments.invoke({
            "ticket_id": ticket_id, "subject": settings.CEO_SUBJECT, "approver": settings.CEO_NAME,
            "metadata": snapshot["metadata"], "draft_content": "", "evaluation": {}, "card": card,
            "revision_count": 0, "status": settings.PENDING, "estimates": {},
        }, self._config(ticket_id, settings.CEO_SUBJECT))

    def _progress(self, ticket_id: int, result: dict) -> dict:
        """No conflict needs settling: say where the ticket stands, and finish it if everything is in."""
        snapshot = self.snapshot(ticket_id)
        sections = snapshot["sections"]
        metadata = snapshot["metadata"]

        rejected = [d for d, s in sections.items() if s["status"] == settings.REJECTED]
        if rejected:
            return self._outcome(ticket_id, "department_rejected", snapshot, result=result, rejected=rejected)

        pending = [d for d, s in sections.items() if s["status"] != settings.APPROVED]
        if pending:
            return self._outcome(ticket_id, "waiting_for_approval", snapshot, result=result)

        if conflict_rules.ceo_required(metadata):
            if snapshot["ceo"] is None:
                self._open_ceo(ticket_id, snapshot)
                snapshot = self.snapshot(ticket_id)
            ceo_status = snapshot["ceo"].get("status")
            if ceo_status == settings.REJECTED:
                return self._outcome(ticket_id, "ceo_rejected", snapshot, result=result)
            if ceo_status != settings.APPROVED:
                return self._outcome(ticket_id, "waiting_for_ceo", snapshot, result=result)

        ceo_status = (snapshot["ceo"] or {}).get("status", settings.PENDING)
        still_open = conflict_rules.detect_conflicts(metadata, sections, ceo_status)["conflicts"]
        approvals = {
            subject: {"status": entry["status"], "approver": settings.APPROVERS[subject],
                      "acted_by": entry.get("acted_by"), "decided_at": entry.get("decided_at"),
                      "comments": entry.get("comments", "")}
            for subject, entry in {**sections, **({settings.CEO_SUBJECT: snapshot["ceo"]} if snapshot["ceo"] else {})}.items()
        }
        try:
            document = final_document.build_final_document(ticket_id, metadata, sections, approvals, still_open)
        except final_document.NotReady as error:
            return self._outcome(ticket_id, "blocked", snapshot, result=result, blockers=error.blockers)
        return self._outcome(ticket_id, "done", snapshot, result=result, document=document)

    def _outcome(self, ticket_id: int, outcome: str, snapshot: dict, result: dict | None = None,
                 arbitration=None, forced=None, rejected=None, blockers=None, document=None) -> dict:
        result = result or {}
        summary = {
            "outcome": outcome,
            "pending": [d for d, s in snapshot["sections"].items() if s["status"] == settings.PENDING],
            "waiting_for": [d for d, s in snapshot["sections"].items() if s["waiting"]]
                           + ([settings.CEO_SUBJECT] if snapshot["ceo"] and snapshot["ceo"]["waiting"] else []),
            "arbitration": arbitration,
            "forced": forced or {},
            "rejected": rejected or [],
            "resolutions": result.get("resolutions", []),
            "conflicts": result.get("conflicts", []),
            "warnings": result.get("warnings", []),
            "blockers": blockers or [],
            "document": document,
        }
        self._event(ticket_id, "approval:coordinate", "ticket_outcome", {
            "outcome": outcome, "waiting_for": summary["waiting_for"], "rejected": summary["rejected"]})
        return summary
