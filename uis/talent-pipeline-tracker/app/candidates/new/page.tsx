"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CandidateCreateInput } from "@/types/candidate";
import { createCandidate } from "@/services/api";
import { validateCandidateForm, CandidateErrors } from "@/lib/validateCandidate";
import CandidateFormFields from "@/components/CandidateFormFields";

const EMPTY: CandidateCreateInput = {
  full_name: "",
  email: "",
  phone: "",
  position: "Executive Assistant",
  linkedin_url: null,
  cv_url: null,
  status: "received",
  stage: "pending",
  experience_years: 0,
};

export default function NewCandidatePage() {
  const router = useRouter();
  const [values, setValues] = useState<CandidateCreateInput>(EMPTY);
  const [errors, setErrors] = useState<CandidateErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  function handleChange(field: keyof CandidateCreateInput, value: string | number | null) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit() {
    const validationErrors = validateCandidateForm(values);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      setFeedback(null);
      return;
    }

    try {
      setSubmitting(true);
      setFeedback(null);
      const created = await createCandidate(values);
      router.push(`/candidates/${created.id}`);
    } catch {
      setFeedback("Could not register candidate. Try again.");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/" className="mb-4 inline-block text-sm text-blue-600 underline">
        ← Back to candidates
      </Link>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Register candidate</h1>

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
          {submitting ? "Registering…" : "Register candidate"}
        </button>
        <Link
          href="/"
          className="rounded-md border border-gray-300 px-5 py-2 text-sm font-medium hover:bg-gray-50"
        >
          Cancel
        </Link>
      </div>
    </main>
  );
}