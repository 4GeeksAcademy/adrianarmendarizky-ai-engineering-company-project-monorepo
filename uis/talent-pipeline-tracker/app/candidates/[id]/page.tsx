"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Candidate, Note } from "@/types/candidate";
import {
  getCandidate,
  patchStatus,
  patchStage,
  getNotes,
  addNote,
  deleteNote,
} from "@/services/api";
import {
  statusLabel,
  stageLabel,
  STATUS_OPTIONS,
  STAGE_OPTIONS,
} from "@/lib/labels";
import { statusTone, stageTone } from "@/lib/tones";
import Badge from "@/components/Badge";

export default function CandidateDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [savingField, setSavingField] = useState<"status" | "stage" | null>(null);
  const [newNote, setNewNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Load candidate + notes on mount.
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const data = await getCandidate(id);
        setCandidate(data);
        setNotes(data.notes ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  async function handleStatusChange(value: string) {
    if (!candidate) return;
    try {
      setSavingField("status");
      setFeedback(null);
      const updated = await patchStatus(candidate.id, value as Candidate["status"]);
      setCandidate(updated);
      setFeedback("Status updated.");
    } catch {
      setFeedback("Could not update status. Try again.");
    } finally {
      setSavingField(null);
    }
  }

  async function handleStageChange(value: string) {
    if (!candidate) return;
    try {
      setSavingField("stage");
      setFeedback(null);
      const updated = await patchStage(candidate.id, value as Candidate["stage"]);
      setCandidate(updated);
      setFeedback("Stage updated.");
    } catch {
      setFeedback("Could not update stage. Try again.");
    } finally {
      setSavingField(null);
    }
  }

  async function handleAddNote() {
    if (!candidate) return;
    if (!newNote.trim()) {
      setNoteError("Note cannot be empty.");
      return;
    }
    try {
      setNoteError(null);
      const created = await addNote(candidate.id, newNote.trim());
      setNotes((prev) => [created, ...prev]);
      setNewNote("");
    } catch {
      setNoteError("Could not add note. Try again.");
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!candidate) return;
    try {
      await deleteNote(candidate.id, noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch {
      setNoteError("Could not delete note. Try again.");
    }
  }

  if (loading) {
    return <main className="mx-auto max-w-3xl px-4 py-8 text-gray-500">Loading candidate…</main>;
  }

  if (error || !candidate) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">
          {error ?? "Candidate not found."}
        </div>
        <Link href="/" className="mt-4 inline-block text-sm text-blue-600 underline">
          Back to candidates
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/" className="mb-4 inline-block text-sm text-blue-600 underline">
        ← Back to candidates
      </Link>

      <header className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{candidate.full_name}</h1>
          <p className="text-gray-500">{candidate.position}</p>
        </div>
        <Link
          href={`/candidates/${candidate.id}/edit`}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
        >
          Edit
        </Link>
      </header>

      {feedback && (
        <div className="mb-4 rounded-md bg-blue-50 p-3 text-sm text-blue-800">{feedback}</div>
      )}

      {/* Fields */}
      <section className="mb-8 grid gap-4 sm:grid-cols-2">
        <Detail label="Email" value={candidate.email} />
        <Detail label="Phone" value={candidate.phone} />
        <Detail label="Years of experience" value={String(candidate.experience_years)} />
        <Detail label="Applied" value={new Date(candidate.applied_at).toLocaleDateString()} />
        <Detail
          label="LinkedIn"
          value={candidate.linkedin_url ? "View profile" : "—"}
          href={candidate.linkedin_url ?? undefined}
        />
        <Detail
          label="CV"
          value={candidate.cv_url ? "Open CV" : "—"}
          href={candidate.cv_url ?? undefined}
        />
      </section>

      {/* Status + stage controls */}
      <section className="mb-8 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-sm font-medium text-gray-700">Status</p>
          <div className="mb-2">
            <Badge label={statusLabel(candidate.status)} tone={statusTone(candidate.status)} />
          </div>
          <select
            value={candidate.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            disabled={savingField === "status"}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <p className="mb-1 text-sm font-medium text-gray-700">Stage</p>
          <div className="mb-2">
            <Badge label={stageLabel(candidate.stage)} tone={stageTone()} />
          </div>
          <select
            value={candidate.stage}
            onChange={(e) => handleStageChange(e.target.value)}
            disabled={savingField === "stage"}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            {STAGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {/* Notes */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">Notes</h2>

        <div className="mb-4 flex gap-2">
          <input
            type="text"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="Add a note after a call or interview"
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            onClick={handleAddNote}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
          >
            Add note
          </button>
        </div>

        {noteError && <p className="mb-3 text-sm text-red-600">{noteError}</p>}

        {notes.length === 0 ? (
          <p className="text-sm text-gray-500">No notes yet.</p>
        ) : (
          <ul className="space-y-2">
            {notes.map((note) => (
              <li
                key={note.id}
                className="flex items-start justify-between rounded-md border border-gray-200 p-3"
              >
                <div>
                  <p className="text-sm text-gray-800">{note.content}</p>
                  <p className="mt-1 text-xs text-gray-400">
                    {new Date(note.created_at).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={() => handleDeleteNote(note.id)}
                  className="ml-3 text-xs text-red-600 hover:underline"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function Detail({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div>
      <p className="text-sm font-medium text-gray-700">{label}</p>
      {href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 underline">
          {value}
        </a>
      ) : (
        <p className="text-sm text-gray-600">{value}</p>
      )}
    </div>
  );
}