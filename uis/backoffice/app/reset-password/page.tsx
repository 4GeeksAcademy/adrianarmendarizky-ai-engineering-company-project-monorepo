"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { resetPassword } from "@/lib/api";

// useSearchParams() needs a Suspense boundary around whatever uses it,
// same reason as /login and /register.
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!token) {
      setError("This reset link is missing its token.");
      return;
    }

    setSubmitting(true);
    try {
      await resetPassword(token, newPassword);
      router.push("/login?reset=success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset your password.");
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <div className="mx-auto max-w-sm">
        <h1 className="text-2xl font-bold text-stone-900 mb-6">Reset password</h1>
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          This reset link is missing its token. Request a new one below.
        </p>
        <p className="mt-4 text-sm text-stone-500">
          <Link href="/forgot-password" className="font-medium text-stone-900 underline">
            Request a new reset link
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold text-stone-900 mb-6">Reset password</h1>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          <p>{error}</p>
          <p className="mt-1">
            <Link href="/forgot-password" className="font-medium underline">
              Request a new reset link
            </Link>
          </p>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-stone-200 bg-white p-5 shadow-sm"
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            New password
          </span>
          <input
            type="password"
            required
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            Confirm new password
          </span>
          <input
            type="password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {submitting ? "Resetting..." : "Reset password"}
        </button>
      </form>
    </div>
  );
}