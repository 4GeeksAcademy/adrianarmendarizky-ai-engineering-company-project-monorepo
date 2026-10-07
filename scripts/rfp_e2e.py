#!/usr/bin/env python
"""
rfp_e2e.py -- a reproducible end-to-end run of the RFP workflow (Milestone 9, Part 3).

It drives ONE RFP through all three parts and plays every human, so nobody has
to click anything:

    Part 1  intake        the PDF is read, classified, split across departments
    Part 2  generation    each department's draft is written and checked
    Part 3  approval      each owner approves (one asks for changes, a cost
                          conflict is settled by its named arbiter, the CEO signs
                          off) and the final document is made

It goes through the real API routes (in this process, no server needed) and the
real pipelines and approval graphs. Only the database is a throwaway SQLite file,
and the human decisions are scripted below (PLAN).

    From services/api:

    uv run python ../../scripts/rfp_e2e.py                 # seeded, offline: no network, a few seconds
    uv run python ../../scripts/rfp_e2e.py --live          # the real sample PDF through Parts 1-3 with
                                                           # the real model (about 6 minutes)
    uv run python ../../scripts/rfp_e2e.py --live --quick  # same, without the rewrite and the conflict
    uv run python ../../scripts/rfp_e2e.py --out ../../docs/rfp-e2e-example.md   # also save the report

Seeded mode starts from a ticket exactly as Parts 1 and 2 leave it (fixtures below)
and runs the whole of Part 3. Live mode starts from the PDF.

Every run ends with a list of consistency checks (ticket statuses only move
forward, the final document holds exactly what each owner approved, the trace is
in order, ...). The exit code is 1 if any check fails.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = REPO_ROOT / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-1.pdf"

APPROVER_EMAIL = "e2e.approver@brasaland.test"

# ---------------------------------------------------------------------------
# The seeded ticket: what Parts 1 and 2 leave behind for the Sunset Bay RFP
# ---------------------------------------------------------------------------

SEED_INPUT = (
    "Seeded from sample RFP #1 (Sunset Bay Resorts, LLC): a co-branded concession at three Florida resort "
    "properties, a new signature menu item, and a budget of $60,000-$75,000 USD a year."
)

SEED_METADATA = {
    "rfp_id": "SBR-2026-0417", "client_name": "Sunset Bay Resorts, LLC", "location": "Florida",
    "service_type": "co-branded concession",
    "scope": "A co-branded concession stand at each of three resort properties",
    "deadline": "September 2, 2026", "budget_range": "$60,000\u2013$75,000 USD",
}

_PRICE = ("- The estimated contract value is $60,000\u2013$75,000 USD per year (240,000,000\u2013300,000,000 COP "
          "at a reference rate of 1 USD = 4,000 COP, to be confirmed).")

# department -> drafts. The first is the seeded draft; the next ones are what a rewrite returns.
DRAFTS = {
    "marketing": [
        "## Brand and Commercial Terms\n\n"
        "- Brasaland proposes a co-branded concession with Sunset Bay Resorts, LLC at its three Florida resort properties.\n"
        "- Our brand pillars are consistent quality, warm experience and speed of service.\n"
        "- The co-branded signature menu item will be exclusive to Sunset Bay Resorts.\n" + _PRICE + "\n"
        "- This offer is valid for 30 days from issuance.",
    ],
    "operaciones": [
        "## Operations and Delivery\n\n"
        "- Brasaland will run one co-branded concession stand at each of the three Florida resort properties.\n"
        "- Service will cover peak season (November\u2013April) and off-season operations.\n"
        "- Setup and launch will take at least 10 business days after contract signing.\n"
        "- Staffing levels for each stand are to be confirmed by Felipe Guerrero.\n" + _PRICE + "\n"
        "- The price per cover is to be confirmed by Felipe Guerrero.",
        "## Operations and Delivery\n\n"
        "- Brasaland will run one co-branded concession stand at each of the three Florida resort properties.\n"
        "- Service will cover peak season (November\u2013April) and off-season operations.\n"
        "- Setup and launch will take at least 10 business days after contract signing.\n"
        "- Each stand is staffed by a crew lead and a kitchen team, sized for peak and off-peak volumes. "
        "The exact number of staff per stand is to be confirmed by Felipe Guerrero.\n" + _PRICE + "\n"
        "- The price per cover is to be confirmed by Felipe Guerrero.",
    ],
    "procurement": [
        "## Ingredient Costs and Supply\n\n"
        "- Ingredients for the signature menu item will be sourced for three resort properties.\n"
        "- Supplier lead times and the ingredient cost per cover are to be confirmed by Lucia Fernandez.\n" + _PRICE,
        "## Ingredient Costs and Supply\n\n"
        "- Ingredients for the signature menu item will be sourced for three resort properties.\n"
        "- Supplier lead times and the ingredient cost per cover are to be confirmed by Lucia Fernandez, "
        "and reviewed once the price per cover is decided.\n" + _PRICE,
    ],
    "training": [
        "## Training and Certification\n\n"
        "- Staff at the three resort properties will be trained on the signature menu item before service starts.\n"
        "- Certification requirements and timing are to be confirmed by Jake Morrison.",
    ],
}

SEED_ASPECTS = {
    "marketing": ["Co-branded concession at three Florida resort properties.", "Exclusive co-branded signature menu item."],
    "operaciones": ["One concession stand at each of three resort properties.",
                    "Peak season (November\u2013April) and off-season service."],
    "procurement": ["Ingredients for the signature menu item at three resort properties."],
    "training": ["Staff training on the new signature menu item."],
}
SEED_QUESTIONS = {
    "marketing": ["What is the desired duration of the exclusivity agreement?"],
    "operaciones": ["What are the expected operating hours for each stand?"],
    "procurement": ["Are there ingredient restrictions at the resort properties?"],
    "training": ["Who at the resorts will attend the training?"],
}

TITLES = {
    "Brand and Commercial Terms": "marketing", "Operations and Delivery": "operaciones",
    "Ingredient Costs and Supply": "procurement", "Training and Certification": "training",
}


class OfflineModel:
    """Stands in for the language model in seeded mode. It only ever has to answer for Part 2's agents,
    because a rewrite (after a request for changes) runs Part 2's real loop: the draft writer returns the
    next canned draft, and the two checkers find nothing wrong."""

    def __init__(self):
        self.rewrites = {}

    def __call__(self, prompt, *, system=None):
        if system and "drafting one section" in system:
            title = re.search(r"belongs to the (.+?) department", system).group(1)
            department = TITLES[title]
            count = self.rewrites[department] = self.rewrites.get(department, 0) + 1
            drafts = DRAFTS[department]
            return drafts[min(count, len(drafts) - 1)]
        if system and "relevance checker" in system:
            return json.dumps({"missing": []})
        if system and "competitor checker" in system:
            return json.dumps({"competitors": []})
        raise AssertionError("seeded mode: the model was asked something it does not expect")


# ---------------------------------------------------------------------------
# The humans: scripted decisions
# ---------------------------------------------------------------------------

PLAN = [
    # Training approves first: the other owners must stay untouched while it waits.
    {"kind": "decide", "subject": "training", "body": {"action": "approve", "comments": "The training plan is clear."}},
    {"kind": "decide", "subject": "marketing", "body": {"action": "approve"}},
    # Operations asks for changes: the draft is rewritten from the comment.
    {"kind": "decide", "subject": "operaciones", "body": {
        "action": "request_changes", "comments": "Please say how many staff each stand needs during peak season."}},
    {"kind": "decide", "subject": "operaciones", "body": {"action": "approve", "estimates": {"price_per_cover_usd": 10}}},
    # Procurement's cost is above Operations' price: the named arbiter has to decide.
    {"kind": "decide", "subject": "procurement", "body": {
        "action": "approve", "estimates": {"ingredient_cost_per_cover_usd": 12}}},
    {"kind": "arbitrate", "trigger": "cost-vs-feasibility", "body": {
        "choice": "raise_price", "comments": "The margin needs a higher price per cover."}},
    # Both go back to their owners: they approve again, with numbers that fit.
    {"kind": "decide", "subject": "operaciones", "body": {"action": "approve", "estimates": {"price_per_cover_usd": 14}}},
    {"kind": "decide", "subject": "procurement", "body": {
        "action": "approve", "estimates": {"ingredient_cost_per_cover_usd": 6}}},
    # Only when the estimated value is above $50,000 a year, and only once everyone else approved.
    {"kind": "decide", "subject": "ceo", "body": {"action": "approve", "comments": "Good margin on this contract."}},
]

QUICK_PLAN = [
    {"kind": "decide", "subject": "training", "body": {"action": "approve"}},
    {"kind": "decide", "subject": "marketing", "body": {"action": "approve"}},
    {"kind": "decide", "subject": "operaciones", "body": {"action": "approve", "estimates": {"price_per_cover_usd": 14}}},
    {"kind": "decide", "subject": "procurement", "body": {
        "action": "approve", "estimates": {"ingredient_cost_per_cover_usd": 6}}},
    {"kind": "decide", "subject": "ceo", "body": {"action": "approve", "comments": "Good margin on this contract."}},
]

# The order tickets move through. A ticket may skip ahead (a seeded ticket starts at under_evaluation)
# but must never go back.
STATUS_ORDER = ["analyzing", "intake_complete", "drafting", "under_evaluation", "needs_human_review",
                "waiting_for_approval", "done"]
DEPARTMENT_ORDER = ["marketing", "operaciones", "procurement", "training"]


def _now() -> str:
    return time.strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run_end_to_end(*, live: bool = False, quick: bool = False, pdf: Path | None = None, log=None,
                   load_env: bool = True) -> dict:
    """Run the whole path and return a report dict. Never leaves the process changed:
    everything it replaces (database, model, approval system) is put back.

    load_env=False skips reading services/api/.env in live mode (the tests do, because they
    replace the two pipelines and never call the real model)."""
    log = log or (lambda message: None)

    os.environ.setdefault("JWT_SECRET_KEY", "e2e-secret")
    os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    original_cwd = Path.cwd()
    api_folder = REPO_ROOT / "services" / "api"
    os.chdir(api_folder)                                   # so .env is found, as when the API runs
    if live and load_env:
        from dotenv import load_dotenv
        load_dotenv(api_folder / ".env")                   # BEFORE the pipeline imports (the API key is read on import)
    for path in (str(api_folder), str(REPO_ROOT / "data" / "pipelines")):
        if path not in sys.path:
            sys.path.insert(0, path)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlmodel import Session, SQLModel, create_engine, select

    import database
    import rfp_approval_service as service
    import routes.rfp as rfp_routes
    import routes.rfp_approval as approval_routes
    from database import get_db
    from dependencies import get_current_user
    from rfp_approval.checkpoint import make_checkpointer
    from rfp_approval.reviser import make_loop_reviser
    from rfp_approval.settings import APPROVERS
    from rfp_approval.system import ApprovalSystem
    from rfp_intake import llm
    from rfp_models import (
        DepartmentSection, RfpApproval, RfpEvent, RfpFinalDocument, RfpMetadata, RfpTicket,
    )
    from user_models import Role

    original_engine, original_model = database.engine, llm.call_generation_llm
    report = {"mode": "live" if live else "seeded", "quick": quick, "timeline": [], "steps": [], "checks": []}
    temp = tempfile.TemporaryDirectory()
    engine = None
    try:
        # --- a throwaway database and a private approval checkpoint --------------------------
        engine = create_engine(f"sqlite:///{Path(temp.name) / 'e2e.db'}",
                               connect_args={"check_same_thread": False, "timeout": 30})
        SQLModel.metadata.create_all(engine, tables=[t.__table__ for t in (
            RfpTicket, RfpMetadata, DepartmentSection, RfpApproval, RfpEvent, RfpFinalDocument)])
        database.engine = engine
        if not live:
            llm.call_generation_llm = OfflineModel()
        service.use_system(ApprovalSystem(
            make_checkpointer(Path(temp.name) / "approvals.db"),
            make_loop_reviser(service._context_for), sink=service._store_event))

        app = FastAPI()
        app.include_router(rfp_routes.router)
        app.include_router(approval_routes.router)

        def _db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(email=APPROVER_EMAIL, role=Role.MANAGER)
        client = TestClient(app)

        # --- helpers ----------------------------------------------------------------------------
        ticket_id = None

        def ticket_row():
            with Session(engine) as db:
                return db.get(RfpTicket, ticket_id)

        def mark(step: str):
            status = ticket_row().status
            report["timeline"].append({"step": step, "status": status, "at": _now()})
            log(f"  [{_now()}] {step}: ticket is {status}")
            return status

        def approvals_now():
            return client.get(f"/rfp/tickets/{ticket_id}/approvals").json()

        def approver_map():
            return {a["subject"]: a for a in approvals_now()["approvers"]}

        # --- Parts 1 and 2: a seeded ticket, or the real PDF -------------------------------------------
        if live:
            pdf = Path(pdf or SAMPLE_PDF)
            log(f"Uploading {pdf.name} and running Parts 1 and 2 with the real model...")
            started = time.time()
            reply = client.post("/rfp/tickets", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
            assert reply.status_code == 202, f"upload refused: {reply.text}"
            ticket_id = reply.json()["ticket_id"]
            status = mark("PDF uploaded and read (Part 1)")
            assert status == "intake_complete", f"Part 1 ended as {status}: {ticket_row().error_message or ticket_row().discard_reason}"
            reply = client.post(f"/rfp/tickets/{ticket_id}/generate")
            assert reply.status_code == 202, f"generate refused: {reply.text}"
            status = mark("Drafts written and checked (Part 2)")
            assert status in ("under_evaluation", "needs_human_review"), f"Part 2 ended as {status}: {ticket_row().error_message}"
            report["input"] = {"file": pdf.name, "bytes": pdf.stat().st_size, "parts_1_and_2_seconds": round(time.time() - started)}
            with Session(engine) as db:
                summary = (ticket_row().sales_summary or {}).get("overview")
            report["input"]["overview"] = summary
        else:
            with Session(engine) as db:
                ticket = RfpTicket(original_filename="CONTEXT-brasaland-request-1.pdf (seeded)", raw_pdf_path="seeded",
                                   status="under_evaluation", rfp_id=SEED_METADATA["rfp_id"])
                db.add(ticket)
                db.commit()
                db.refresh(ticket)
                ticket_id = ticket.id
                db.add(RfpMetadata(
                    ticket_id=ticket_id, client_name=SEED_METADATA["client_name"], location=SEED_METADATA["location"],
                    service_type=SEED_METADATA["service_type"], scope=SEED_METADATA["scope"],
                    deadline=SEED_METADATA["deadline"], budget_range=SEED_METADATA["budget_range"], language="en",
                    departments_needed=list(DEPARTMENT_ORDER)))
                for department in DEPARTMENT_ORDER:
                    db.add(DepartmentSection(
                        ticket_id=ticket_id, department_id=department, key_aspects=SEED_ASPECTS[department],
                        open_questions=SEED_QUESTIONS[department], draft_content=DRAFTS[department][0],
                        evaluation_results={
                            "department_id": department, "section_status": "passed", "iterations": 1, "history": [],
                            "error": None, "readability": {"pass": True, "score": None, "details": "too short to score"},
                            "relevance": {"pass": True, "missing_aspects": []},
                            "compliance": {"pass": True, "rule_ids": [], "violations": []},
                            "overall_pass": True, "feedback_for_generator": ""}))
                db.commit()
            mark("Ticket seeded as Parts 1 and 2 leave it")
            report["input"] = {"file": "CONTEXT-brasaland-request-1.pdf (seeded)", "overview": SEED_INPUT}

        with Session(engine) as db:
            meta = db.exec(select(RfpMetadata).where(RfpMetadata.ticket_id == ticket_id)).first()
            report["input"]["metadata"] = {
                f: getattr(meta, f) for f in ("client_name", "location", "service_type", "scope", "deadline", "budget_range")}
            sections = db.exec(select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)).all()
        departments = [d for d in DEPARTMENT_ORDER if d in {s.department_id for s in sections}]
        report["input"]["departments"] = departments
        report["ticket_id"] = ticket_id

        # --- Part 3: send for approval, then play every human -------------------------------------------
        log("Sending the ticket for approval (Part 3)...")
        reply = client.post(f"/rfp/tickets/{ticket_id}/send-for-approval")
        assert reply.status_code == 200, f"send-for-approval refused: {reply.text}"
        mark("Sent for approval")

        drafts_before = {}
        last_outcome = reply.json()["outcome"]["outcome"]
        ceo_opened_with = None
        first_decision_checked = False
        executed = []
        for number, step in enumerate(QUICK_PLAN if quick else PLAN, 1):
            kind = step["kind"]
            record = {"n": number, "kind": kind, "who": step.get("subject") or step.get("trigger"), "body": step["body"]}

            if kind == "arbitrate":
                if last_outcome != "arbitration_pending":
                    record["skipped"] = "no conflict was open"
                    report["steps"].append(record)
                    continue
                report["final_document_blocked"] = (            # looked at WHILE the conflict is open
                    ticket_row().status == "waiting_for_approval"
                    and client.get(f"/rfp/tickets/{ticket_id}/final-document").status_code == 404)
                reply = client.post(f"/rfp/tickets/{ticket_id}/arbitration/{step['trigger']}", json=step["body"])
            else:
                subject = step["subject"]
                present = approver_map()
                if subject not in present:
                    record["skipped"] = "not an approver on this ticket" if subject != "ceo" else "the CEO was not asked"
                    report["steps"].append(record)
                    continue
                if subject == "ceo" and ceo_opened_with is None:
                    ceo_opened_with = {s: a["status"] for s, a in present.items() if s != "ceo"}
                if step["body"]["action"] == "request_changes":
                    drafts_before[subject] = (present[subject]["draft_content"], present[subject]["revision_count"])
                reply = client.post(f"/rfp/tickets/{ticket_id}/approvals/{subject}", json=step["body"])
                executed.append((subject, step["body"]["action"]))

            if reply.status_code != 200:
                record["error"] = f"{reply.status_code}: {reply.json().get('detail')}"
                report["steps"].append(record)
                raise AssertionError(f"step {number} ({record['who']}) failed: {record['error']}")
            answer = reply.json()
            last_outcome = answer["outcome"]["outcome"]
            record["outcome"] = last_outcome
            record["waiting_for"] = answer["outcome"]["waiting_for"]
            report["steps"].append(record)
            log(f"  [{_now()}] {number}. {record['who']} {step['body'].get('action') or step['body'].get('choice')}"
                f" -> {last_outcome}")

            if kind == "decide" and not first_decision_checked:
                first_decision_checked = True
                others = [a for a in answer["approvals"]["approvers"] if a["subject"] != step["subject"]]
                report["others_waited"] = bool(others) and all(a["status"] == "pending" and a["waiting"] for a in others)
            if step["body"].get("action") == "request_changes":
                after = approver_map()[step["subject"]]
                before_text, before_count = drafts_before[step["subject"]]
                report["rewrite"] = {
                    "department": step["subject"], "changed": after["draft_content"] != before_text,
                    "revisions": after["revision_count"], "before_revisions": before_count}
            mark(f"After step {number} ({record['who']})")

        # --- what came out ------------------------------------------------------------------------------
        final_reply = client.get(f"/rfp/tickets/{ticket_id}/final-document")
        report["final_document"] = final_reply.json() if final_reply.status_code == 200 else None
        final_approvers = approver_map()
        report["final_approvers"] = final_approvers
        trace = client.get(f"/rfp/tickets/{ticket_id}/trace", params={"limit": 2000}).json()
        report["trace"] = trace
        with Session(engine) as db:
            report["ticket_final"] = {"status": ticket_row().status, "error_message": ticket_row().error_message}
            report["section_texts"] = {
                s.department_id: s.draft_content for s in db.exec(
                    select(DepartmentSection).where(DepartmentSection.ticket_id == ticket_id)).all()}
            report["approval_rows"] = {
                a.subject: {"status": a.status, "acted_by": a.acted_by, "decided_at": str(a.decided_at)} for a in db.exec(
                    select(RfpApproval).where(RfpApproval.ticket_id == ticket_id)).all()}
            stored_doc = db.exec(select(RfpFinalDocument).where(RfpFinalDocument.ticket_id == ticket_id)).first()
        report["executed"] = executed
        report["ceo_opened_with"] = ceo_opened_with
        report["owners"] = APPROVERS

        _run_checks(report, departments, stored_doc is not None, live)
    finally:
        database.engine = original_engine
        llm.call_generation_llm = original_model
        service.use_system(None)
        if engine is not None:
            engine.dispose()
        os.chdir(original_cwd)
        temp.cleanup()

    report["ok"] = all(check["ok"] for check in report["checks"])
    return report


# ---------------------------------------------------------------------------
# Consistency checks
# ---------------------------------------------------------------------------

def trace_is_in_order(trace: list) -> bool:
    """True if the trace reads as one story, from the PDF to the final document.

    Events come back in the order they were saved. In that order the parts must never go back
    (Part 1, then Part 2, then Part 3), and time must not go back by more than a second: two
    departments running at the same moment can stamp their events a few milliseconds out of
    order, and that is not a problem."""
    ids = [e["id"] for e in trace]
    parts = [e["part"] for e in trace]
    stamps = [datetime.fromisoformat(e["created_at"]) for e in trace]
    return (ids == sorted(ids) and parts == sorted(parts)
            and all(later - earlier >= -timedelta(seconds=1) for earlier, later in zip(stamps, stamps[1:])))


def _run_checks(report: dict, departments: list, document_saved: bool, live: bool) -> None:
    checks = report["checks"]

    def check(name: str, ok: bool, detail: str = ""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    # 1. statuses only move forward
    seen = []
    for entry in report["timeline"]:
        if not seen or seen[-1] != entry["status"]:
            seen.append(entry["status"])
    known = all(s in STATUS_ORDER for s in seen)
    forward = known and all(STATUS_ORDER.index(a) <= STATUS_ORDER.index(b) for a, b in zip(seen, seen[1:]))
    check("The ticket's status only ever moves forward, through known statuses", forward, " -> ".join(seen))

    final = report["ticket_final"]
    check("The ticket ends as done, with no error message left over",
          final["status"] == "done" and not final["error_message"], f"status={final['status']}, message={final['error_message']}")

    document = report["final_document"]
    check("The final document exists and is stored", document is not None and document_saved)
    if document is None:
        return

    # 2. who is in it
    in_doc = [s["department_id"] for s in document["sections"]]
    owners_ok = all(s["approver"] == report["owners"][s["department_id"]] for s in document["sections"])
    check("Every department that applies is in the final document, in the fixed order, under its owner's name",
          in_doc == departments and owners_ok, f"{in_doc}")

    # 3. what is in it: exactly what each owner last approved
    same = all(s["content"] == report["section_texts"][s["department_id"]] == report["final_approvers"][s["department_id"]]["draft_content"]
               for s in document["sections"])
    check("The final document holds exactly the text each owner last approved (and what is stored)", same)

    title_ok = document["markdown"].startswith(f"# Proposal for {report['input']['metadata']['client_name']}")
    check("The document is for the client in the RFP", title_ok)

    budget = report["input"]["metadata"].get("budget_range") or ""
    has_value = document["total_estimated_value"] is not None
    check("The estimated value is shown only if the RFP states a budget", has_value == bool(re.search(r"\d", budget)))

    # 4. approvals
    rows = report["approval_rows"]
    approved = all(r["status"] == "approved" and r["acted_by"] == APPROVER_EMAIL and r["decided_at"] != "None"
                   for r in rows.values())
    expected_rows = set(departments) | ({"ceo"} if "ceo" in rows else set())
    check("Every approver is recorded as approved, with who recorded it and when",
          approved and set(rows) == expected_rows, f"{sorted(rows)}")
    check("Nothing is left waiting", all(a["status"] == "approved" and not a["waiting"] for a in report["final_approvers"].values()))

    # 5. the behaviours the ticket asks to prove
    if "others_waited" in report:
        check("Approving one department left the others waiting, untouched", report["others_waited"])
    if "rewrite" in report:
        rewrite = report["rewrite"]
        check("Asking for changes rewrote the draft and counted as a revision",
              rewrite["changed"] and rewrite["revisions"] == rewrite["before_revisions"] + 1,
              f"{rewrite['department']}: revisions {rewrite['before_revisions']} -> {rewrite['revisions']}")
    if "final_document_blocked" in report:
        check("While a conflict was open the final document could not be made", report["final_document_blocked"])
    if report["ceo_opened_with"] is not None:
        check("The CEO was only asked once every department had approved",
              all(status == "approved" for status in report["ceo_opened_with"].values()), str(report["ceo_opened_with"]))

    # 6. the trace
    trace = report["trace"]
    parts = {e["part"] for e in trace}
    expected_parts = {1, 2, 3} if live else {3}
    check("The trace is in order (Part 1, then 2, then 3) and covers the parts that ran",
          bool(trace) and trace_is_in_order(trace) and parts == expected_parts,
          f"{len(trace)} events, parts {sorted(parts)}")
    humans = [(e["subject"], e["output"].get("action")) for e in trace if e["event_type"] == "human_decision"]
    cursor, matched = 0, True
    for wanted in report["executed"]:
        try:
            cursor = humans.index(wanted, cursor) + 1
        except ValueError:
            matched = False
            break
    check("Every human decision is in the trace, in order, with who made it",
          matched and all(e["actor"] == APPROVER_EMAIL for e in trace if e["event_type"] == "human_decision"))


# ---------------------------------------------------------------------------
# The report (Markdown, ready to paste into a PR)
# ---------------------------------------------------------------------------

def render_report(report: dict) -> str:
    lines = [f"# RFP end-to-end run ({report['mode']}{', quick' if report.get('quick') else ''})", ""]
    verdict = "ALL CHECKS PASSED" if report["ok"] else "SOME CHECKS FAILED"
    lines += [f"**{verdict}**", ""]

    info = report["input"]
    lines += ["## Input RFP", "", f"- File: `{info['file']}`"]
    if info.get("overview"):
        lines.append(f"- Summary: {info['overview']}")
    meta = info["metadata"]
    lines += [f"- Client: {meta['client_name']} ({meta['location']})", f"- Service: {meta['service_type']}",
              f"- Scope: {meta['scope']}", f"- Deadline: {meta['deadline']}", f"- Budget: {meta['budget_range']}",
              f"- Departments that apply: {', '.join(info['departments'])}", ""]

    lines += ["## Ticket states", "", "| Time | Step | Ticket status |", "|---|---|---|"]
    timeline = report["timeline"]
    for index, entry in enumerate(timeline):
        changed = index == 0 or entry["status"] != timeline[index - 1]["status"] or index == len(timeline) - 1
        if changed:
            lines.append(f"| {entry['at']} | {entry['step']} | `{entry['status']}` |")
    lines += ["", f"(the status was checked after all {len(timeline)} steps; only the changes are listed)"]

    lines += ["", "## Simulated approvals", "",
              "| # | Who | Decision | What they said or entered | What happened | Still waiting for |", "|---|---|---|---|---|---|"]
    for step in report["steps"]:
        body = step["body"]
        said = body.get("comments", "")
        numbers = ", ".join(f"{k.replace('_', ' ')} = {v}" for k, v in body.get("estimates", {}).items())
        said = " ".join(part for part in (f"\"{said}\"" if said else "", numbers) if part) or "-"
        decision = body.get("action") or f"arbiter chose {body.get('choice')}"
        result = step.get("skipped") and f"skipped ({step['skipped']})" or step.get("outcome", step.get("error", ""))
        who = report["owners"].get(step["who"], step["who"]) if step["kind"] == "decide" else f"arbiter ({step['who']})"
        label = f"{step['who']} ({who})" if step["kind"] == "decide" else who
        waiting = ", ".join(step.get("waiting_for", [])) or "-"
        if step.get("outcome") == "arbitration_pending":
            waiting = "the arbiter (Camila Ospina)"
        lines.append(f"| {step['n']} | {label} | {decision} | {said} | `{result}` | {waiting} |")

    if report.get("final_document"):
        lines += ["", "## Final document", "", "````markdown", report["final_document"]["markdown"].rstrip(), "````"]

    parts = {}
    for event in report["trace"]:
        parts[event["part"]] = parts.get(event["part"], 0) + 1
    lines += ["", "## Trace", "",
              "One trace for the whole ticket: " + ", ".join(f"Part {p}: {n} events" for p, n in sorted(parts.items())) + ".",
              "", "| Part | Agent | Subject | By |", "|---|---|---|---|"]
    for event in report["trace"][:12]:
        lines.append(f"| {event['part']} | `{event['agent']}` | {event['subject'] or ''} | {event['actor'] or ''} |")
    if len(report["trace"]) > 12:
        lines.append(f"| ... | {len(report['trace']) - 12} more events | | |")

    lines += ["", "## Consistency checks", ""]
    lines += [f"- {'PASS' if c['ok'] else 'FAIL'}: {c['name']}" + (f" ({c['detail']})" if c["detail"] else "") for c in report["checks"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one RFP through intake, generation and approval, with scripted humans.")
    parser.add_argument("--live", action="store_true", help="use the real sample PDF and the real model (about 6 minutes)")
    parser.add_argument("--quick", action="store_true", help="skip the rewrite and the conflict (a shorter run)")
    parser.add_argument("--pdf", type=Path, help="the PDF to use with --live (default: sample RFP #1)")
    parser.add_argument("--out", type=Path, help="also save the report to this Markdown file")
    args = parser.parse_args()

    print(f"Running the {'live' if args.live else 'seeded, offline'} end-to-end path...", flush=True)
    try:
        report = run_end_to_end(live=args.live, quick=args.quick, pdf=args.pdf, log=lambda m: print(m, flush=True))
    except AssertionError as error:
        print(f"\nSTOPPED: {error}")
        return 1
    text = render_report(report)
    print("\n" + text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"Report saved to {args.out}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
