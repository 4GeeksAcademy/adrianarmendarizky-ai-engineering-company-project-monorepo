"use client";

// RFP intake and response (Milestone 9, Parts 1 and 2) -- the ticket-mode page
// Sales uses.
//
// Upload a PDF and one ticket is created. While any ticket is analyzing, or its
// drafts are being written, the page asks the API for fresh data every 2
// seconds, and stops on its own once nothing is running. Click a row to read
// the result: what each department needs and who to ask (Part 1), and the
// draft proposal for each department (Part 2).
//
// "Generate draft proposal" starts the drafts. Each department shows what it is
// doing right now, then its draft and how it was checked. A section that did
// not pass the checks is shown as a provisional draft that needs a person.
//
// Client component because it uploads a file and polls.

import { useEffect, useState, type FormEvent } from "react";
import {
  generateDrafts,
  getTicket,
  listTickets,
  uploadRfp,
  type SectionEvaluation,
  type TicketDetail,
  type TicketListItem,
  type TicketSection,
  type TicketStatus,
} from "@/lib/rfp";
import ApprovalPanel, { RFP_CHANGED_EVENT } from "./ApprovalPanel";

const STATUS_STYLE: Record<TicketStatus, string> = {
  analyzing: "bg-yellow-100 text-yellow-800",
  intake_complete: "bg-green-100 text-green-800",
  discarded: "bg-gray-200 text-gray-700",
  failed: "bg-red-100 text-red-800",
  drafting: "bg-blue-100 text-blue-800",
  under_evaluation: "bg-indigo-100 text-indigo-800",
  needs_human_review: "bg-amber-100 text-amber-800",
  waiting_for_approval: "bg-purple-100 text-purple-800",
  done: "bg-emerald-100 text-emerald-800",
};

// A ticket can get drafts when it finished intake, or when a finished run
// should be done again. Never while one is running.
const CAN_GENERATE: TicketStatus[] = ["intake_complete", "under_evaluation", "needs_human_review"];

function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status]}`}>
      {status}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="text-sm">
        {value === null || value === "" ? (
          <span className="italic text-gray-400">Not stated in the RFP</span>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso + "Z").toLocaleString();
}

function stageLabel(evaluation: SectionEvaluation): string {
  const draft = evaluation.iteration ?? 0;
  if (evaluation.stage === "drafting") return `Writing draft #${draft}…`;
  if (evaluation.stage === "evaluating") return `Checking draft #${draft}…`;
  return "Waiting to start…";
}

function EvaluationDetails({ evaluation }: { evaluation: SectionEvaluation }) {
  const readability = evaluation.readability;
  const relevance = evaluation.relevance;
  const compliance = evaluation.compliance;

  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-gray-600">How this draft was checked</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>Drafts written: {evaluation.iterations ?? "—"}</li>
        {readability && (
          <li>
            Readability: {readability.pass ? "passed" : "did not pass"} — {readability.details}
          </li>
        )}
        {relevance && (
          <li>
            Covers what the RFP asks for: {relevance.pass ? "yes" : "no"}
            {relevance.missing_aspects.length > 0 && (
              <ul className="list-disc pl-5">
                {relevance.missing_aspects.map((item, i) => (
                  <li key={i}>Missing: {item}</li>
                ))}
              </ul>
            )}
          </li>
        )}
        {compliance && (
          <li>
            Company guidelines: {compliance.pass ? "all met" : "not all met"}
            {compliance.violations.length > 0 && (
              <ul className="list-disc pl-5">
                {compliance.violations.map((v, i) => (
                  <li key={i}>
                    <span className="font-mono text-xs">{v.rule_id}</span> — {v.message}
                    {v.evidence && <span className="italic"> (“{v.evidence}”)</span>}
                  </li>
                ))}
              </ul>
            )}
          </li>
        )}
      </ul>
    </details>
  );
}

function DraftCard({ section }: { section: TicketSection }) {
  const evaluation = section.evaluation_results;
  if (!evaluation) return null;

  const running = evaluation.section_status === "running";
  const needsReview = evaluation.section_status === "needs_human_review";

  return (
    <div className={`rounded border p-3 ${needsReview ? "border-amber-400 bg-amber-50" : ""}`}>
      <h4 className="font-medium">
        {section.department_id}{" "}
        {running && (
          <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
            in progress
          </span>
        )}
        {evaluation.section_status === "passed" && (
          <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
            passed the checks
          </span>
        )}
        {needsReview && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            needs human review
          </span>
        )}
      </h4>

      {running && <p className="mt-2 text-sm text-gray-600">{stageLabel(evaluation)}</p>}

      {needsReview && (
        <p className="mt-2 rounded bg-amber-100 p-2 text-sm text-amber-900">
          <strong>Provisional draft.</strong>{" "}
          {section.draft_content
            ? `This section did not pass the checks after ${evaluation.iterations ?? "several"} draft(s), so a person needs to review it before it goes to the client.`
            : "No draft could be produced for this section."}
          {evaluation.error && <> Problem: {evaluation.error}</>}
        </p>
      )}

      {section.draft_content && (
        <pre className="mt-2 whitespace-pre-wrap font-sans text-sm">{section.draft_content}</pre>
      )}

      {!running && <EvaluationDetails evaluation={evaluation} />}
    </div>
  );
}

function TicketView({
  ticket,
  onGenerate,
  busy,
}: {
  ticket: TicketDetail;
  onGenerate: () => void;
  busy: boolean;
}) {
  const meta = ticket.metadata;
  const summary = ticket.sales_summary;
  const canGenerate = CAN_GENERATE.includes(ticket.status) && !ticket.generation_running;
  const hasDrafts = ticket.sections.some((s) => s.evaluation_results !== null);

  return (
    <section className="mt-6 rounded border p-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">
          Ticket #{ticket.ticket_id} — {ticket.original_filename}
        </h2>
        <StatusBadge status={ticket.status} />
      </div>

      {ticket.status === "analyzing" && (
        <p className="mt-3 text-sm text-gray-600">
          Reading the PDF and splitting the work across departments…
        </p>
      )}

      {ticket.status === "discarded" && (
        <p className="mt-3 text-sm">
          <strong>Not an RFP.</strong> {ticket.discard_reason ?? "No reason was saved."}
        </p>
      )}

      {ticket.status === "failed" && (
        <p className="mt-3 text-sm text-red-700">
          <strong>Something went wrong:</strong> {ticket.error_message ?? "Unknown error."}
        </p>
      )}

      {ticket.status === "intake_complete" && ticket.error_message && (
        <p className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900">
          <strong>The last attempt to write the drafts did not finish:</strong> {ticket.error_message}
        </p>
      )}

      {meta && ticket.status === "discarded" && (
        <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Language" value={meta.language} />
          <Field
            label="Readability"
            value={
              meta.flesch_kincaid !== null && meta.gunning_fog !== null
                ? `Flesch-Kincaid ${meta.flesch_kincaid.toFixed(1)} · Gunning Fog ${meta.gunning_fog.toFixed(1)} · ${meta.word_count} words`
                : meta.readability_note
            }
          />
        </dl>
      )}

      {meta && ticket.status !== "discarded" && (
        <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Client" value={meta.client_name} />
          <Field label="Location" value={meta.location} />
          <Field label="Service" value={meta.service_type} />
          <Field label="Deadline" value={meta.deadline} />
          <Field label="Budget" value={meta.budget_range} />
          <Field label="Language" value={meta.language} />
          <div className="sm:col-span-2">
            <Field label="Scope" value={meta.scope} />
          </div>
          <div className="sm:col-span-2">
            <Field
              label="Readability"
              value={
                meta.flesch_kincaid !== null && meta.gunning_fog !== null
                  ? `Flesch-Kincaid ${meta.flesch_kincaid.toFixed(1)} · Gunning Fog ${meta.gunning_fog.toFixed(1)} · ${meta.word_count} words`
                  : meta.readability_note
              }
            />
          </div>
        </dl>
      )}

      {summary && (
        <div className="mt-6">
          <h3 className="font-semibold">Summary for Sales</h3>
          <p className="mt-1 text-sm">{summary.overview}</p>

          {summary.missing_fields.length > 0 && (
            <p className="mt-2 text-sm text-amber-700">
              Not stated in the RFP: {summary.missing_fields.join(", ")}
            </p>
          )}
          {summary.other_departments_mentioned.length > 0 && (
            <p className="mt-2 text-sm text-amber-700">
              Departments mentioned that are not in our process:{" "}
              {summary.other_departments_mentioned.join(", ")}
            </p>
          )}

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {summary.departments.map((dept) => (
              <div key={dept.department_id} className="rounded border p-3">
                <h4 className="font-medium">
                  {dept.department_id}{" "}
                  <span className="text-sm font-normal text-gray-500">
                    — ask {dept.owner}
                  </span>
                </h4>
                <p className="mt-2 text-xs uppercase tracking-wide text-gray-500">
                  What they need to know
                </p>
                <ul className="list-disc pl-5 text-sm">
                  {dept.key_aspects.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
                {dept.open_questions.length > 0 && (
                  <>
                    <p className="mt-2 text-xs uppercase tracking-wide text-gray-500">
                      Still to ask the client
                    </p>
                    <ul className="list-disc pl-5 text-sm">
                      {dept.open_questions.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <ApprovalPanel
        ticketId={ticket.ticket_id}
        status={ticket.status}
        generationRunning={ticket.generation_running}
      />

      {(canGenerate || ticket.generation_running || hasDrafts) && (
        <div className="mt-8 border-t pt-4">
          <h3 className="font-semibold">Draft proposal</h3>

          {canGenerate && (
            <div className="mt-2">
              <button
                type="button"
                onClick={onGenerate}
                disabled={busy}
                className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
              >
                {busy
                  ? "Starting…"
                  : hasDrafts
                    ? "Generate again"
                    : "Generate draft proposal"}
              </button>
              {hasDrafts && (
                <span className="ml-3 text-xs text-gray-500">This replaces the current drafts.</span>
              )}
            </div>
          )}

          {ticket.generation_running && (
            <p className="mt-2 text-sm text-gray-600">
              The drafts are being written and checked. This page updates by itself.
            </p>
          )}

          {!ticket.generation_running && ticket.average_iterations !== null && (
            <p className="mt-2 text-sm text-gray-600">
              Average drafts per section: {ticket.average_iterations}
            </p>
          )}

          {ticket.status === "needs_human_review" && (
            <p className="mt-2 text-sm text-amber-800">
              At least one section did not pass the checks. Those drafts are marked provisional below.
            </p>
          )}

          {hasDrafts && (
            <div className="mt-4 grid gap-4">
              {ticket.sections.map((section) => (
                <DraftCard key={section.department_id} section={section} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default function RfpPage() {
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Bumping this number makes the effect below load fresh data.
  const [reloadKey, setReloadKey] = useState(0);

  // Loads the list, and the open ticket if there is one. Runs on the first
  // render, whenever another ticket is selected, and whenever reloadKey changes.
  // State is only set once the data has arrived (inside .then), never
  // straight away.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listTickets(),
      selectedId !== null ? getTicket(selectedId) : Promise.resolve(null),
    ])
      .then(([rows, ticket]) => {
        if (cancelled) return;
        setTickets(rows);
        setDetail(ticket);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Could not load the tickets.");
      });
    return () => {
      cancelled = true; // ignore an answer that arrives after we moved on
    };
  }, [selectedId, reloadKey]);

  // While a ticket is being analyzed, its drafts are being written, or it is waiting
  // for approval, ask for fresh data every 2 seconds. Stops on its own once nothing
  // is running or waiting.
  const needsPolling = tickets.some(
    (t) => t.status === "analyzing" || t.generation_running || t.status === "waiting_for_approval"
  );
  useEffect(() => {
    if (!needsPolling) return;
    const timer = setInterval(() => setReloadKey((k) => k + 1), 2000);
    return () => clearInterval(timer);
  }, [needsPolling]);

  // The approvals panel announces when something it did changes the ticket (for example
  // sending it for approval), so the badge and the list update at once, not only when the
  // 2-second refresh happens to be running.
  useEffect(() => {
    const reload = () => setReloadKey((k) => k + 1);
    window.addEventListener(RFP_CHANGED_EVENT, reload);
    return () => window.removeEventListener(RFP_CHANGED_EVENT, reload);
  }, []);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    const form = event.currentTarget; // grab it now: it is gone after the await
    setUploading(true);
    setError(null);
    try {
      const created = await uploadRfp(file);
      setFile(null);
      form.reset();
      setSelectedId(created.ticket_id);
      setReloadKey((k) => k + 1); // reload the list so the new ticket shows up
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not upload the RFP.");
    } finally {
      setUploading(false);
    }
  }

  async function handleGenerate(ticketId: number) {
    setGenerating(true);
    setError(null);
    try {
      await generateDrafts(ticketId);
      setReloadKey((k) => k + 1); // the ticket now says "drafting", and polling starts
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the drafts.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold">RFP intake</h1>
      <p className="mt-1 text-sm text-gray-600">
        Upload a client RFP (PDF). Sales can read what each department needs
        without opening the document, and generate a first draft of the proposal.
      </p>

      <form onSubmit={handleUpload} className="mt-4 flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept="application/pdf,.pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        <button
          type="submit"
          disabled={!file || uploading}
          className="rounded bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          {uploading ? "Uploading…" : "Upload RFP"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

      <table className="mt-6 w-full text-left text-sm">
        <thead>
          <tr className="border-b text-xs uppercase tracking-wide text-gray-500">
            <th className="py-2 pr-4">#</th>
            <th>File</th>
            <th>Client</th>
            <th>Departments</th>
            <th>Status</th>
            <th>Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {tickets.length === 0 && (
            <tr>
              <td colSpan={6} className="py-4 text-gray-500">
                No tickets yet. Upload a PDF to start one.
              </td>
            </tr>
          )}
          {tickets.map((t) => (
            <tr
              key={t.ticket_id}
              onClick={() => setSelectedId(t.ticket_id)}
              className={`cursor-pointer border-b hover:bg-gray-50 ${
                t.ticket_id === selectedId ? "bg-gray-100" : ""
              }`}
            >
              <td className="py-2 pr-4">{t.ticket_id}</td>
              <td>{t.original_filename}</td>
              <td>{t.client_name ?? "—"}</td>
              <td>{t.departments_needed.length ? t.departments_needed.join(", ") : "—"}</td>
              <td>
                <StatusBadge status={t.status} />
              </td>
              <td>{formatDate(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {detail && selectedId === detail.ticket_id && (
        <TicketView
          ticket={detail}
          onGenerate={() => handleGenerate(detail.ticket_id)}
          busy={generating}
        />
      )}
    </div>
  );
}
