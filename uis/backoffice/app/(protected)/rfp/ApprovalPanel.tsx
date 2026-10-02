"use client";

// ApprovalPanel.tsx  (Milestone 9, Part 3)
//
// The approvals part of the RFP page. It shows, for one ticket:
//   - a "Send for approval" button once the drafts are ready
//   - one card per approver (each department, and the CEO when the estimated
//     value is above $50,000 USD a year) with the draft they are asked to
//     approve, and buttons to approve, ask for changes, or reject
//   - the conflict a named arbiter has to settle, when there is one
//   - the final document once everyone has approved
//   - a trace of everything that happened, in order
//
// It only talks to the API through lib/rfp.ts. Only managers and admins see the
// decision buttons (the API enforces the same rule, so this is a convenience).
// The panel reloads by itself every few seconds while a ticket is waiting, so
// an approval made by someone else shows up without a refresh.

import { useEffect, useState } from "react";
import { getMe } from "@/lib/api";
import {
  answerArbitration,
  continueRewrite,
  getApprovals,
  getFinalDocument,
  getTrace,
  recordDecision,
  sendForApproval,
  type ApprovalAction,
  type ApprovalAnswer,
  type Approvals,
  type Approver,
  type DecisionBody,
  type FinalDocument,
  type TicketStatus,
  type TraceEvent,
} from "@/lib/rfp";

const DEPARTMENT_LABEL: Record<string, string> = {
  marketing: "Marketing",
  operaciones: "Operations",
  procurement: "Procurement",
  training: "Training",
  ceo: "CEO",
};

// The two approvers who enter a number the cost-versus-feasibility check compares.
const ESTIMATE_FIELD: Record<string, { key: string; label: string }> = {
  procurement: { key: "ingredient_cost_per_cover_usd", label: "Ingredient cost per cover (USD)" },
  operaciones: { key: "price_per_cover_usd", label: "Price per cover (USD)" },
};

const ARBITRATION_CHOICE_LABEL: Record<string, string> = {
  raise_price: "Raise the price",
  reduce_scope: "Reduce the scope",
};

const STATUS_CHIP: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
};

// Same minimum the API asks for when someone rejects or asks for changes.
const MIN_COMMENT_LENGTH = 10;

const CAN_SEND: TicketStatus[] = ["under_evaluation", "needs_human_review"];

// Announced on the window after anything this panel does that can change the ticket
// (sending it for approval, an approval, a decision), so the page can reload at once.
export const RFP_CHANGED_EVENT = "rfp-changed";

function labelOf(subject: string): string {
  return DEPARTMENT_LABEL[subject] ?? subject;
}

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  // The server sends UTC times without a "Z" on the end. Add it, so the browser
  // shows the time in the user's own time zone instead of reading it as local time.
  const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(iso);
  return new Date(hasZone ? iso : `${iso}Z`).toLocaleString("en-US");
}

function usd(value: number): string {
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

// ---------------------------------------------------------------------------
// The checks a draft went through, in a few words
// ---------------------------------------------------------------------------

function EvaluationSummary({ approver }: { approver: Approver }) {
  const evaluation = approver.evaluation;
  if (!evaluation || evaluation.overall_pass === undefined || evaluation.overall_pass === null) return null;
  if (evaluation.overall_pass) {
    return <p className="mt-2 text-xs text-green-700">Passed all the automatic checks.</p>;
  }
  const problems: string[] = [];
  if (evaluation.readability?.pass === false) {
    problems.push(`Readability grade ${evaluation.readability.score ?? "?"} is above the limit.`);
  }
  for (const aspect of evaluation.relevance?.missing_aspects ?? []) {
    problems.push(`Does not cover: ${aspect}`);
  }
  for (const violation of evaluation.compliance?.violations ?? []) {
    problems.push(violation.message ?? violation.rule_id ?? "A rule was broken.");
  }
  return (
    <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
      <p className="font-medium">Did not pass every automatic check. Please read it carefully.</p>
      {problems.length > 0 && (
        <ul className="mt-1 list-disc pl-4">
          {problems.map((problem, index) => (
            <li key={index}>{problem}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The answer form of one approver
// ---------------------------------------------------------------------------

function DecisionForm({
  approver,
  working,
  disabled,
  onDecide,
}: {
  approver: Approver;
  working: boolean;
  disabled: boolean;
  onDecide: (subject: string, body: DecisionBody) => void;
}) {
  const [comments, setComments] = useState("");
  const [estimate, setEstimate] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const field = ESTIMATE_FIELD[approver.subject];
  const isCeo = approver.subject === "ceo";

  function submit(action: ApprovalAction) {
    setProblem(null);
    const text = comments.trim();
    if (action !== "approve" && text.length < MIN_COMMENT_LENGTH) {
      setProblem(`Say why, in at least ${MIN_COMMENT_LENGTH} characters, to ${action === "reject" ? "reject" : "ask for changes"}.`);
      return;
    }
    const body: DecisionBody = { action };
    if (text) body.comments = text;
    if (action === "approve" && field && estimate.trim() !== "") {
      const value = Number(estimate);
      if (!Number.isFinite(value) || value <= 0) {
        setProblem(`${field.label} must be a number above zero.`);
        return;
      }
      body.estimates = { [field.key]: value };
    }
    onDecide(approver.subject, body);
  }

  return (
    <div className="mt-3 border-t pt-3">
      <label className="block text-xs font-medium text-gray-700" htmlFor={`comments-${approver.subject}`}>
        Comments {isCeo ? "(needed to reject)" : "(needed to reject or ask for changes)"}
      </label>
      <textarea
        id={`comments-${approver.subject}`}
        className="mt-1 w-full rounded border p-2 text-sm"
        rows={2}
        value={comments}
        disabled={disabled}
        onChange={(event) => setComments(event.target.value)}
      />
      {field && (
        <div className="mt-2">
          <label className="block text-xs font-medium text-gray-700" htmlFor={`estimate-${approver.subject}`}>
            {field.label} <span className="font-normal text-gray-500">(optional; used to check cost against price)</span>
          </label>
          <input
            id={`estimate-${approver.subject}`}
            className="mt-1 w-40 rounded border p-1 text-sm"
            inputMode="decimal"
            value={estimate}
            disabled={disabled}
            onChange={(event) => setEstimate(event.target.value)}
          />
        </div>
      )}
      {problem && <p role="alert" className="mt-2 text-xs text-red-700">{problem}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded bg-green-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={disabled}
          onClick={() => submit("approve")}
        >
          Approve
        </button>
        {!isCeo && (
          <button
            type="button"
            className="rounded bg-amber-500 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={disabled || approver.revisions_left === 0}
            onClick={() => submit("request_changes")}
          >
            Ask for changes
          </button>
        )}
        <button
          type="button"
          className="rounded bg-red-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          disabled={disabled}
          onClick={() => submit("reject")}
        >
          Reject
        </button>
      </div>
      {!isCeo && (
        <p className="mt-2 text-xs text-gray-500">
          Changes asked for so far: {approver.revision_count} of {approver.revision_count + approver.revisions_left}.
          {approver.revisions_left === 0 && " No more changes can be asked for: approve or reject."}
        </p>
      )}
      {working && (
        <p className="mt-2 text-xs text-gray-600">
          Working… rewriting a section after a request for changes can take up to a minute.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One approver
// ---------------------------------------------------------------------------

function ApproverCardView({
  approver,
  canAct,
  busy,
  onDecide,
  onContinue,
}: {
  approver: Approver;
  canAct: boolean;
  busy: string | null;
  onDecide: (subject: string, body: DecisionBody) => void;
  onContinue: (subject: string) => void;
}) {
  const interrupted = approver.status === "pending" && !approver.waiting;
  const chipText = interrupted ? "Rewrite interrupted" : approver.status === "pending" ? "Waiting for approval" : approver.status;
  const chipStyle = interrupted ? "bg-orange-100 text-orange-800" : STATUS_CHIP[approver.status];
  const card = approver.card;

  return (
    <article className="mt-3 rounded border bg-white p-3" data-testid={`approver-${approver.subject}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">
          {labelOf(approver.subject)} — {approver.approver}
        </h4>
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${chipStyle}`}>{chipText}</span>
      </div>

      {approver.status === "approved" && (
        <p className="mt-1 text-xs text-gray-600">
          Approved by {approver.acted_by ?? "someone"} on {formatWhen(approver.decided_at)}.
          {approver.comments && <> “{approver.comments}”</>}
          {Object.entries(approver.estimates).map(([key, value]) => (
            <span key={key}> {key.replace(/_/g, " ")}: {usd(value)}.</span>
          ))}
        </p>
      )}
      {approver.status === "rejected" && (
        <p className="mt-1 text-xs text-red-700">
          Rejected{approver.acted_by ? ` by ${approver.acted_by}` : ""}: {approver.rejected_reason ?? approver.comments}
        </p>
      )}

      {approver.subject === "ceo" ? (
        <div className="mt-2 text-sm">
          {card.estimated_annual_value_usd && (
            <p>
              Estimated yearly value: {usd(card.estimated_annual_value_usd.low)}
              {card.estimated_annual_value_usd.low !== card.estimated_annual_value_usd.high &&
                ` to ${usd(card.estimated_annual_value_usd.high)}`}{" "}
              USD, above the {usd(card.threshold_usd ?? 50000)} that needs the CEO.
            </p>
          )}
          <p className="mt-1 text-xs text-gray-600">
            Approved by the departments:{" "}
            {(card.approved_sections ?? []).map((s) => `${labelOf(s.department_id)} (${s.approver})`).join(", ") || "none yet"}.
          </p>
        </div>
      ) : (
        <details className="mt-2" open={approver.status === "pending"}>
          <summary className="cursor-pointer text-xs font-medium text-gray-700">The draft</summary>
          <pre className="mt-1 whitespace-pre-wrap rounded bg-gray-50 p-2 text-sm">{approver.draft_content}</pre>
        </details>
      )}

      {approver.subject !== "ceo" && <EvaluationSummary approver={approver} />}

      {approver.subject !== "ceo" && (card.open_questions ?? []).length > 0 && approver.status === "pending" && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-gray-700">Open questions for the client</summary>
          <ul className="mt-1 list-disc pl-5 text-xs text-gray-700">
            {(card.open_questions ?? []).map((question, index) => (
              <li key={index}>{question}</li>
            ))}
          </ul>
        </details>
      )}

      {interrupted && (
        <div className="mt-3 rounded border border-orange-200 bg-orange-50 p-2 text-xs text-orange-800">
          <p>The rewrite was cut short before it finished. Nothing was lost.</p>
          {canAct && (
            <button
              type="button"
              className="mt-2 rounded bg-orange-600 px-3 py-1 text-white disabled:opacity-50"
              disabled={busy !== null}
              onClick={() => onContinue(approver.subject)}
            >
              {busy === approver.subject ? "Continuing…" : "Continue the rewrite"}
            </button>
          )}
        </div>
      )}

      {approver.status === "pending" && approver.waiting && canAct && (
        <DecisionForm
          key={approver.revision_count}
          approver={approver}
          working={busy === approver.subject}
          disabled={busy !== null}
          onDecide={onDecide}
        />
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// The conflict a named arbiter settles
// ---------------------------------------------------------------------------

function ArbitrationBox({
  approvals,
  canAct,
  busy,
  onArbitrate,
}: {
  approvals: Approvals;
  canAct: boolean;
  busy: string | null;
  onArbitrate: (trigger: string, body: { choice: string; comments: string }) => void;
}) {
  const request = approvals.arbitration;
  const [choice, setChoice] = useState("");
  const [comments, setComments] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  if (!request) return null;

  const cost = Number(request.details.ingredient_cost_per_cover_usd);
  const price = Number(request.details.price_per_cover_usd);

  function submit() {
    setProblem(null);
    if (!choice) {
      setProblem("Choose what to do.");
      return;
    }
    if (comments.trim().length < MIN_COMMENT_LENGTH) {
      setProblem(`Say why, in at least ${MIN_COMMENT_LENGTH} characters.`);
      return;
    }
    onArbitrate(request!.trigger, { choice, comments: comments.trim() });
  }

  return (
    <div className="mt-3 rounded border border-red-200 bg-red-50 p-3" data-testid="arbitration">
      <h4 className="text-sm font-semibold text-red-800">A conflict needs a decision</h4>
      <p className="mt-1 text-sm text-red-900">
        Cost against feasibility: the ingredients cost {usd(cost)} per cover, which is more than the price of{" "}
        {usd(price)} per cover. {request.arbiter} decides what happens next. Nothing else moves until then.
      </p>
      {canAct ? (
        <>
          <fieldset className="mt-2">
            <legend className="text-xs font-medium text-gray-700">What should happen?</legend>
            {request.choices.map((option) => (
              <label key={option} className="mr-4 text-sm">
                <input
                  type="radio"
                  name="arbitration-choice"
                  className="mr-1"
                  value={option}
                  checked={choice === option}
                  disabled={busy !== null}
                  onChange={() => setChoice(option)}
                />
                {ARBITRATION_CHOICE_LABEL[option] ?? option}
              </label>
            ))}
          </fieldset>
          <label className="mt-2 block text-xs font-medium text-gray-700" htmlFor="arbitration-comments">
            Why
          </label>
          <textarea
            id="arbitration-comments"
            className="mt-1 w-full rounded border p-2 text-sm"
            rows={2}
            value={comments}
            disabled={busy !== null}
            onChange={(event) => setComments(event.target.value)}
          />
          {problem && <p role="alert" className="mt-1 text-xs text-red-700">{problem}</p>}
          <button
            type="button"
            className="mt-2 rounded bg-red-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={busy !== null}
            onClick={submit}
          >
            {busy === "arbitration" ? "Recording…" : "Record the decision"}
          </button>
          <p className="mt-1 text-xs text-gray-600">
            Both sections go back to their owners with this decision as the reason.
          </p>
        </>
      ) : (
        <p className="mt-2 text-xs text-gray-600">Only managers and admins can record this decision.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The final document
// ---------------------------------------------------------------------------

function downloadMarkdown(document_: FinalDocument) {
  const blob = new Blob([document_.markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `proposal-ticket-${document_.ticket_id}.md`;
  link.click();
  URL.revokeObjectURL(url);
}

export function FinalDocumentView({ document_ }: { document_: FinalDocument }) {
  const value = document_.total_estimated_value;
  return (
    <div className="mt-3 rounded border border-green-200 bg-green-50 p-3" data-testid="final-document">
      <h4 className="text-sm font-semibold text-green-800">The final proposal is ready</h4>
      <p className="mt-1 text-xs text-gray-700">
        Made on {formatWhen(document_.generated_at)} from the sections everyone approved.
        {value
          ? ` Estimated yearly value: ${usd(value.usd_low)}${value.usd_low !== value.usd_high ? ` to ${usd(value.usd_high)}` : ""} USD.`
          : " The RFP does not state a budget."}
      </p>
      <ul className="mt-1 list-disc pl-5 text-xs text-gray-700">
        {document_.approvals.map((approval) => (
          <li key={approval.subject}>
            {labelOf(approval.subject)}: approved by {approval.approver}
            {approval.acted_by ? ` (recorded by ${approval.acted_by})` : ""}
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="mt-2 rounded bg-green-700 px-3 py-1 text-sm text-white"
        onClick={() => downloadMarkdown(document_)}
      >
        Download as a Markdown file
      </button>
      <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-white p-2 text-sm">
        {document_.markdown}
      </pre>
    </div>
  );
}

function FinalDocumentBox({ ticketId }: { ticketId: number }) {
  const [loaded, setLoaded] = useState<{ ticketId: number; document: FinalDocument } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getFinalDocument(ticketId)
      .then((data) => {
        if (!cancelled) setLoaded({ ticketId, document: data });
      })
      .catch((e) => {
        if (!cancelled) setProblem(e instanceof Error ? e.message : "Could not load the final document.");
      });
    return () => {
      cancelled = true;
    };
  }, [ticketId]);

  if (problem) return <p role="alert" className="mt-3 text-sm text-red-700">{problem}</p>;
  if (!loaded || loaded.ticketId !== ticketId) return <p className="mt-3 text-sm text-gray-600">Loading the final document…</p>;
  return <FinalDocumentView document_={loaded.document} />;
}

// ---------------------------------------------------------------------------
// The trace: every step, in order
// ---------------------------------------------------------------------------

export function TraceView({ events }: { events: TraceEvent[] }) {
  if (events.length === 0) return <p className="mt-2 text-xs text-gray-600">Nothing has happened yet.</p>;
  return (
    <ol className="mt-2 space-y-1 text-xs" data-testid="trace">
      {events.map((event) => {
        const action = event.event_type === "human_decision" ? String(event.output?.action ?? "") : "";
        const comments = event.event_type === "human_decision" ? String(event.output?.comments ?? "") : "";
        return (
          <li key={event.id} className="rounded border bg-white p-1">
            <span className="text-gray-500">{formatWhen(event.created_at)}</span>{" "}
            <span className="text-gray-500">Part {event.part} ·</span>{" "}
            <span className="font-medium">{event.agent}</span>
            {event.subject && <span> · {labelOf(event.subject)}</span>}
            {event.actor && <span> · by {event.actor}</span>}
            {action && <span> · {action}</span>}
            {comments && <span className="text-gray-600"> “{comments}”</span>}
            <details className="inline-block pl-2 align-top">
              <summary className="cursor-pointer text-gray-500">details</summary>
              <pre className="whitespace-pre-wrap text-gray-700">
                {JSON.stringify({ input: event.input, output: event.output }, null, 2)}
              </pre>
            </details>
          </li>
        );
      })}
    </ol>
  );
}

function TraceBox({ ticketId }: { ticketId: number }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<TraceEvent[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getTrace(ticketId)
      .then((data) => {
        if (!cancelled) setEvents(data);
      })
      .catch((e) => {
        if (!cancelled) setProblem(e instanceof Error ? e.message : "Could not load the trace.");
      });
    return () => {
      cancelled = true;
    };
  }, [open, ticketId]);

  return (
    <div className="mt-4">
      <button type="button" className="text-xs font-medium text-indigo-700 underline" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide what happened" : "Show everything that happened, step by step"}
      </button>
      {open && problem && <p role="alert" className="mt-1 text-xs text-red-700">{problem}</p>}
      {open && !problem && (events === null ? <p className="mt-1 text-xs text-gray-600">Loading…</p> : <TraceView events={events} />)}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The panel as a whole (the view takes everything as props, so it is easy to test)
// ---------------------------------------------------------------------------

export function ApprovalView({
  ticketId,
  status,
  generationRunning,
  approvals,
  canDecide,
  busy,
  error,
  onSend,
  onDecide,
  onContinue,
  onArbitrate,
}: {
  ticketId: number;
  status: TicketStatus;
  generationRunning: boolean;
  approvals: Approvals | null;
  canDecide: boolean;
  busy: string | null;
  error: string | null;
  onSend: () => void;
  onDecide: (subject: string, body: DecisionBody) => void;
  onContinue: (subject: string) => void;
  onArbitrate: (trigger: string, body: { choice: string; comments: string }) => void;
}) {
  const shown = CAN_SEND.includes(status) || status === "waiting_for_approval" || status === "done";
  if (!shown) return null;

  const canAct = canDecide && status === "waiting_for_approval";
  const showCards =
    approvals !== null &&
    approvals.started &&
    (status === "waiting_for_approval" || status === "done" || (status === "needs_human_review" && !!approvals.message));
  const approvedCount = approvals ? approvals.approvers.filter((a) => a.status === "approved").length : 0;
  const total = approvals ? approvals.approvers.length : 0;

  return (
    <section className="mt-6 rounded border border-indigo-200 bg-indigo-50/40 p-4" data-testid="approval-panel">
      <h3 className="text-base font-semibold">Approvals</h3>

      {error && (
        <p role="alert" className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {CAN_SEND.includes(status) && (
        <div className="mt-2">
          {approvals?.message && (
            <p className="mb-2 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800">
              The last round ended: {approvals.message}
            </p>
          )}
          <p className="text-sm text-gray-700">
            When the drafts look right, send them to the department owners. Each owner approves their own
            section. The final document is made only once everyone has approved.
          </p>
          <button
            type="button"
            className="mt-2 rounded bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            disabled={busy !== null || generationRunning}
            onClick={onSend}
          >
            {busy === "send" ? "Sending…" : "Send for approval"}
          </button>
          {generationRunning && <p className="mt-1 text-xs text-gray-600">The drafts are still being written.</p>}
        </div>
      )}

      {status === "waiting_for_approval" && (
        <p className="mt-1 text-sm text-gray-700">
          {approvedCount} of {total} approvals in.
          {!canDecide && " Only managers and admins can record approvals."}
        </p>
      )}

      {approvals && approvals.warnings.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">
          {approvals.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      )}

      {status === "waiting_for_approval" && approvals && approvals.arbitration && (
        <ArbitrationBox approvals={approvals} canAct={canAct} busy={busy} onArbitrate={onArbitrate} />
      )}

      {status === "waiting_for_approval" &&
        approvals &&
        approvals.conflicts
          .filter((conflict) => conflict.trigger === "ceo-threshold")
          .map((conflict) => (
            <p key={conflict.trigger} className="mt-2 text-xs text-gray-700">
              The estimated value is above $50,000 a year, so {conflict.arbiter} must approve before the final
              document is made.
            </p>
          ))}

      {showCards &&
        approvals.approvers.map((approver) => (
          <ApproverCardView
            key={approver.subject}
            approver={approver}
            canAct={canAct}
            busy={busy}
            onDecide={onDecide}
            onContinue={onContinue}
          />
        ))}

      {status === "done" && <FinalDocumentBox ticketId={ticketId} />}

      <TraceBox ticketId={ticketId} />
    </section>
  );
}

export default function ApprovalPanel({
  ticketId,
  status,
  generationRunning,
}: {
  ticketId: number;
  status: TicketStatus;
  generationRunning: boolean;
}) {
  const [approvals, setApprovals] = useState<Approvals | null>(null);
  const [canDecide, setCanDecide] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Who is looking: only managers and admins get the decision buttons.
  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) setCanDecide(me.role === "manager" || me.role === "admin");
      })
      .catch(() => {
        // not being able to tell just means no decision buttons
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The approvals of this ticket. While it waits, ask again every few seconds so
  // another approver's answer shows up without a refresh.
  useEffect(() => {
    const relevant = CAN_SEND.includes(status) || status === "waiting_for_approval" || status === "done";
    if (!relevant) return;
    let cancelled = false;
    const load = () =>
      getApprovals(ticketId)
        .then((data) => {
          if (!cancelled) setApprovals(data);
        })
        .catch((e) => {
          if (!cancelled) setError(e instanceof Error ? e.message : "Could not load the approvals.");
        });
    load();
    if (status !== "waiting_for_approval") {
      return () => {
        cancelled = true;
      };
    }
    const timer = setInterval(load, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [ticketId, status, reloadKey]);

  async function run(label: string, call: () => Promise<ApprovalAnswer>) {
    setBusy(label);
    setError(null);
    try {
      const answer = await call();
      setApprovals(answer.approvals);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
      setReloadKey((k) => k + 1); // show what the server really says now
      window.dispatchEvent(new Event(RFP_CHANGED_EVENT)); // and tell the page, so its badge updates too
    }
  }

  const current = approvals && approvals.ticket_id === ticketId ? approvals : null;

  return (
    <ApprovalView
      ticketId={ticketId}
      status={status}
      generationRunning={generationRunning}
      approvals={current}
      canDecide={canDecide}
      busy={busy}
      error={error}
      onSend={() => run("send", () => sendForApproval(ticketId))}
      onDecide={(subject, body) => run(subject, () => recordDecision(ticketId, subject, body))}
      onContinue={(subject) => run(subject, () => continueRewrite(ticketId, subject))}
      onArbitrate={(trigger, body) => run("arbitration", () => answerArbitration(ticketId, trigger, body))}
    />
  );
}
