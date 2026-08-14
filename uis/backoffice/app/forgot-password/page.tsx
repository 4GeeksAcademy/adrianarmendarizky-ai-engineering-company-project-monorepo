"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    // Same outcome shown whether the address is registered or not, and
    // even if the request itself fails -- there's nothing useful or
    // safe to tell an unauthenticated visitor beyond this either way.
    try {
      await forgotPassword(email);
    } catch {
      // intentionally ignored -- see above
    } finally {
      setSubmitting(false);
      setSubmitted(true);
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
      )}

      <p className="mt-4 text-sm text-stone-500">
        <Link href="/login" className="font-medium text-stone-900 underline">
          Back to log in
        </Link>
      </p>
    </div>
  );
}