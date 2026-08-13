"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/api";
import { setToken } from "@/lib/auth";

// useSearchParams() requires a Suspense boundary around whatever uses
// it, or Next.js can't statically prerender the rest of the page --
// so the actual form lives in a child component, wrapped below.
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("returnTo");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const token = await login(email, password);
      setToken(token);

      if (returnTo) {
        // We were sent here by a different app (Incidents, Talent
        // Pipeline Tracker) that has no login of its own. Hand the
        // token back via a URL fragment rather than a query param --
        // fragments never get sent to the server, so it won't show up
        // in any access log or Referer header, only in the receiving
        // app's own JS. This is a full page navigation (not
        // router.push) because returnTo is a different origin.
        window.location.href = `${returnTo}#token=${encodeURIComponent(token)}`;
        return;
      }

      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log in.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold text-stone-900 mb-6">Log in</h1>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-stone-200 bg-white p-5 shadow-sm"
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            Password
          </span>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {submitting ? "Logging in..." : "Log in"}
        </button>
      </form>

      <p className="mt-4 text-sm text-stone-500">
        Need an account?{" "}
        <Link
          href={returnTo ? `/register?returnTo=${encodeURIComponent(returnTo)}` : "/register"}
          className="font-medium text-stone-900 underline"
        >
          Register
        </Link>
      </p>
    </div>
  );
}