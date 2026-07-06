"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import { CandidateCreateInput } from "@/types/candidate";
import { getCandidate, updateCandidate } from "@/services/api";
import { validateCandidateForm, CandidateErrors } from "@/lib/validateCandidate";
import CandidateFormFields from "@/components/CandidateFormFields";

export default function EditCandidatePage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [values, setValues] = useState<CandidateCreateInput | null>(null);
  const [errors, setErrors] = useState<CandidateErrors>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Load the existing candidate and pre-fill the form.
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setLoadError(null);
        const c = await getCandidate(id);
        setValues({
          full_name: c.full_name,
          email: c.email,
          phone: c.phone,
          position: c.position,
          linkedin_url: c.linkedin_url,
          cv_url: c.cv_url,
          status: c.status,
          stage: c.stage,
          experience_years: c.experience_years,
        });
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  function handleChange(field: keyof CandidateCreateInput, value: string | number | null) {
    setValues((prev) => (prev ? { ...prev, [field]: value } : prev));
  }

  async function handleSubmit() {
    if (!values) return;
    const validationErrors = validateCandidateForm(values);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      setFeedback(null);
      return;
    }

    try {
      setSubmitting(true);
      setFeedback(null);
      await updateCandidate(id, values);
      router.push(`/candidates/${id}`);
    } catch {
      setFeedback("Could not save changes. Try again.");
      setSubmitting(false);
    }
  }

  if (loading) {
    return <main className="mx-auto max-w-3xl px-4 py-8 text-gray-500">Loading…</main>;
  }

  if (loadError || !values) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">
          {loadError ?? "Candidate not found."}
        </div>
        <Link href="/" className="mt-4 inline-block text-sm text-blue-600 underline">
          Back to candidates
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href={`/candidates/${id}`} className="mb-4 inline-block text-sm text-blue-600 underline">
        ← Back to candidate
      </Link>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Edit candidate</h1>

      {feedback && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{feedback}</div>
      )}

      <CandidateFormFields values={values} errors={errors} onChange={handleChange} />

      <div className="mt-6 flex gap-3">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="rounded-md bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save changes"}
        </button>
        <Link
          href={`/candidates/${id}`}
          className="rounded-md border border-gray-300 px-5 py-2 text-sm font-medium hover:bg-gray-50"
        >
          Cancel
        </Link>
      </div>
    </main>
  );
}