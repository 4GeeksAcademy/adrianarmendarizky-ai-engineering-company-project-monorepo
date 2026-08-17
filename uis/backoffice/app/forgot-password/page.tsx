"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitFailed, setSubmitFailed] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitFailed(false);
    try {
      await forgotPassword(email);
      setSubmitted(true);
    } catch {
      setSubmitFailed(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold text-stone-900 mb-6">
        Forgot your password?
      </h1>

      {submitted ? (
        <p className="rounded-lg border border-stone-200 bg-white p-5 text-sm text-stone-700 shadow-sm">
          If that address is registered, you&apos;ll receive a reset link
          shortly. Check your inbox.
        </p>
      ) : (
        <div className="space-y-3">
          {submitFailed && (
            <div className="rounded-lg border border-stone-200 bg-white p-4 text-sm text-stone-700 shadow-sm">
              <p>We couldn&apos;t process that request right now.</p>
              <button
                type="button"
                onClick={() => setSubmitFailed(false)}
                className="mt-3 rounded-lg border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
              >
                Try again
              </button>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-xl border border-stone-200 bg-white p-5 shadow-sm"
          >
            <label className="block text-sm">
              <span className="mb-1 block font-medium text-stone-700">
                Email
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
              />
            </label>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {submitting ? "Sending..." : "Send reset link"}
            </button>
          </form>
        </div>
      )}

      <p className="mt-4 text-sm text-stone-500">
        <Link href="/login" className="font-medium text-stone-900 underline">
          Back to log in
        </Link>
      </p>
    </div>
  );
}