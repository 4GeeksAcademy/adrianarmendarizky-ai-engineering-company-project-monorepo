"""
final_document.py -- builds the final proposal from the APPROVED sections
(Milestone 9, Part 3).

The shape is CONTEXT-brasaland.md section 2.3's FinalDocument: ticket_id,
sections, total_estimated_value, generated_at (plus who approved what).

build_final_document() refuses to run unless everything CONTEXT requires is in
place, and says exactly what is missing (NotReady.blockers):
  - every department that applies has approved its section
  - the CEO has approved, when the estimated value is above $50,000 USD a year
  - no conflict from section 7 is still open
That is what makes the document "generated only once every department has
given approval", enforced in code and not just in a diagram.
"""

from datetime import datetime, timezone

from rfp_intake.state import DEPARTMENT_IDS
from rfp_response import settings as response_settings
from rfp_response.generator import DEPARTMENTS

from . import conflicts as conflict_rules
from . import settings


class NotReady(Exception):
    """The final document can't be built yet. .blockers says why."""

    def __init__(self, blockers):
        self.blockers = list(blockers)
        super().__init__("; ".join(self.blockers))


def blockers(departments, approvals: dict, ceo_needed: bool, open_conflicts: list) -> list[str]:
    """Everything still standing between this ticket and its final document."""
    found = []
    for department_id in departments:
        status = (approvals.get(department_id) or {}).get("status", settings.PENDING)
        if status != settings.APPROVED:
            found.append(
                f"{department_id}: {settings.APPROVERS[department_id]} has not approved (status: {status})"
            )
    if ceo_needed:
        status = (approvals.get(settings.CEO_SUBJECT) or {}).get("status", settings.PENDING)
        if status != settings.APPROVED:
            found.append(f"ceo: {settings.CEO_NAME} has not approved (status: {status})")
    for conflict in open_conflicts:
        if conflict["trigger"] == settings.TRIGGER_CEO:
            continue  # already reported above as the CEO's missing approval
        found.append(f"open conflict: {conflict['trigger']} (arbiter: {conflict['arbiter']})")
    return found


def _total_estimated_value(metadata: dict):
    value = conflict_rules.estimated_annual_value_usd(metadata)
    if value is None:
        return None
    rate = response_settings.COP_PER_USD
    return {
        "usd_low": value["low"], "usd_high": value["high"],
        "cop_low": value["low"] * rate, "cop_high": value["high"] * rate,
        "reference_rate_cop_per_usd": rate,
        "note": "From the budget stated in the RFP. The COP figures use a reference rate, to be confirmed.",
    }


def build_final_document(ticket_id: int, metadata: dict, sections: dict, approvals: dict,
                         open_conflicts: list, now: datetime | None = None) -> dict:
    """sections: department_id -> {"draft_content": str}
    approvals: subject ("marketing" ... "ceo") -> {"status", "approver", "acted_by",
               "decided_at", "comments"}
    """
    departments = [d for d in DEPARTMENT_IDS if d in sections]
    ceo_needed = conflict_rules.ceo_required(metadata)

    missing = blockers(departments, approvals, ceo_needed, open_conflicts)
    if missing:
        raise NotReady(missing)

    now = now or datetime.now(timezone.utc).replace(tzinfo=None)

    def entry(subject):
        approval = approvals[subject]
        return {
            "subject": subject,
            "approver": approval.get("approver") or settings.APPROVERS[subject],
            "acted_by": approval.get("acted_by"),
            "approved_at": approval.get("decided_at"),
            "comments": approval.get("comments") or "",
        }

    return {
        "ticket_id": ticket_id,
        "client_name": (metadata or {}).get("client_name"),
        "rfp_id": (metadata or {}).get("rfp_id"),
        "sections": [
            {
                "department_id": department_id,
                "title": DEPARTMENTS[department_id]["title"],
                "content": sections[department_id]["draft_content"],
                **{k: v for k, v in entry(department_id).items() if k in ("approver", "acted_by", "approved_at")},
            }
            for department_id in departments
        ],
        "approvals": [entry(subject) for subject in departments + ([settings.CEO_SUBJECT] if ceo_needed else [])],
        "total_estimated_value": _total_estimated_value(metadata),
        "generated_at": now.isoformat(),
    }


def render_markdown(document: dict) -> str:
    """The final document as one readable Markdown file."""
    lines = [f"# Proposal for {document.get('client_name') or 'the client'}", ""]
    reference = f"RFP reference: {document['rfp_id']} | " if document.get("rfp_id") else ""
    lines.append(f"{reference}Ticket #{document['ticket_id']} | Generated: {document['generated_at']}")
    lines.append("")

    value = document.get("total_estimated_value")
    if value:
        lines.append(
            f"**Estimated annual value:** ${value['usd_low']:,.0f}\u2013${value['usd_high']:,.0f} USD "
            f"({value['cop_low']:,.0f}\u2013{value['cop_high']:,.0f} COP at a reference rate of "
            f"1 USD = {value['reference_rate_cop_per_usd']:,.0f} COP, to be confirmed)."
            if value["usd_low"] != value["usd_high"] else
            f"**Estimated annual value:** ${value['usd_high']:,.0f} USD "
            f"({value['cop_high']:,.0f} COP at a reference rate of "
            f"1 USD = {value['reference_rate_cop_per_usd']:,.0f} COP, to be confirmed)."
        )
    else:
        lines.append("**Estimated annual value:** not stated in the RFP.")
    lines.append("")

    for section in document["sections"]:
        content = (section["content"] or "").strip()
        if not content.startswith("#"):
            content = f"## {section['title']}\n\n{content}"
        lines += [content, ""]

    lines += ["## Approvals", "", "| Approver | Role | Recorded by | Date |", "|---|---|---|---|"]
    for approval in document["approvals"]:
        role = "CEO" if approval["subject"] == settings.CEO_SUBJECT else approval["subject"]
        lines.append(
            f"| {approval['approver']} | {role} | {approval['acted_by'] or '-'} | {approval['approved_at'] or '-'} |"
        )
    return "\n".join(lines) + "\n"
