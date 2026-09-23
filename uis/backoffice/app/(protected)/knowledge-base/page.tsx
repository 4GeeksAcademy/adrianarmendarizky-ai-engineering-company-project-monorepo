"use client";

// Knowledge Base assistant -- Milestone 7 (RAG & Knowledge Base).
// One text box, one POST to /knowledge/query, one generated answer shown
// back. No chunks, no scores, no sources list rendered here -- the
// endpoint only ever returns { answer: string } (see
// services/api/routes/knowledge.py), which is itself the point: the
// person asking never has to know Qdrant or an LLM is involved.
//
// Client component (like the suppliers/reporting pages) because
// submitting the question re-fetches without a full page reload.

import { useState, type FormEvent } from "react";
import { queryKnowledge } from "@/lib/api";

const EXAMPLE_QUESTIONS = [
  "How many points does a customer need for Gold tier?",
  "Does the BBQ Ribs dish have any allergens?",
  "How often do we order beverages from suppliers?",
];

export default function KnowledgeBasePage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function ask(q: string) {
    if (!q.trim()) return;
    setLoading(true);
    setLoadError(null);
    setAnswer(null);
    try {
      setAnswer(await queryKnowledge(q));
    } catch (err) {
      // A failed call must not look like an empty/no-info answer -- the
      // ticket's Phase 4 checklist calls this out explicitly.
      setLoadError(
        err instanceof Error ? `Could not get an answer: ${err.message}` : "Could not get an answer."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    ask(question);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Knowledge Base Assistant</h1>
        <p className="text-sm text-stone-500 mt-1">
          Ask about the loyalty program, allergens, waste protocol, or supplier ordering --
          answered from Brasaland&apos;s official manuals, the way a trained salesperson would.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. How many points do I need for Gold tier?"
          className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {loading ? "Asking..." : "Ask"}
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => {
              setQuestion(q);
              ask(q);
            }}
            className="rounded-full border border-stone-300 px-3 py-1 text-xs text-stone-600 hover:bg-stone-200"
          >
            {q}
          </button>
        ))}
      </div>

      {loadError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {loadError}
        </div>
      )}

      {loading && !loadError && (
        <div className="rounded-xl border border-stone-200 bg-white p-4 text-sm text-stone-500">
          Looking that up...
        </div>
      )}

      {answer && !loading && (
        <div className="rounded-xl bg-white p-5 shadow-sm border border-stone-200">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-500 mb-2">
            Answer
          </p>
          <p className="text-sm text-stone-900 whitespace-pre-wrap">{answer}</p>
        </div>
      )}
    </div>
  );
}
