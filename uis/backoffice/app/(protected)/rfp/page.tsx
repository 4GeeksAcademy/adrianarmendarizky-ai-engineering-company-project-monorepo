"use client";

// RFP intake (Milestone 9, Part 1) -- the ticket-mode page Sales uses.
//
// Upload a PDF and one ticket is created. While any ticket is "analyzing"
// the page asks the API for fresh data every 2 seconds, and stops on its own
// once every ticket is intake_complete, discarded, or failed. Click a row to
// read the result: what each department needs, and who to ask.
//
// Client component because it uploads a file and polls.

import { useEffect, useState, type FormEvent } from "react";
import {
  getTicket,
  listTickets,
  uploadRfp,
  type TicketDetail,
  type TicketListItem,
  type TicketStatus,
} from "@/lib/rfp";

const STATUS_STYLE: Record<TicketStatus, string> = {
  analyzing: "bg-yellow-100 text-yellow-800",
  intake_complete: "bg-green-100 text-green-800",
  discarded: "bg-gray-200 text-gray-700",
  failed: "bg-red-100 text-red-800",
};

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

function TicketView({ ticket }: { ticket: TicketDetail }) {
  const meta = ticket.metadata;
  const summary = ticket.sales_summary;

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
    </section>
  );
}

export default function RfpPage() {
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
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

  // While some ticket is still analyzing, ask for fresh data every 2 seconds.
  // Stops on its own once every ticket is finished.
  const anyAnalyzing = tickets.some((t) => t.status === "analyzing");
  useEffect(() => {
    if (!anyAnalyzing) return;
    const timer = setInterval(() => setReloadKey((k) => k + 1), 2000);
    return () => clearInterval(timer);
  }, [anyAnalyzing]);

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

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold">RFP intake</h1>
      <p className="mt-1 text-sm text-gray-600">
        Upload a client RFP (PDF). Sales can read what each department needs
        without opening the document.
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

      {detail && selectedId === detail.ticket_id && <TicketView ticket={detail} />}
    </div>
  );
}
