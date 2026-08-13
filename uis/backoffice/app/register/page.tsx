"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { login, registerUser } from "@/lib/api";
import { setToken } from "@/lib/auth";

type FieldErrors = { email?: string; password?: string };

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("returnTo");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (!email.trim()) errors.email = "Email is required.";
    // Matches the backend's UserCreate.password min_length=8.
    if (password.length < 8) {
      errors.password = "Password must be at least 8 characters.";
    }
    return errors;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      // Two separate backend calls, per the brief: POST /users to
      // create the account, then POST /auth/login with the same
      // credentials -- so the person doesn't have to type their
      // password a second time on a separate screen.
      await registerUser({
        email,
        password,
        name: name.trim() || undefined,
        phone: phone.trim() || undefined,
        address: address.trim() || undefined,
      });
      const token = await login(email, password);
      setToken(token);

      if (returnTo) {
        window.location.href = `${returnTo}#token=${encodeURIComponent(token)}`;
        return;
      }

      router.push("/");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not register.");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-bold text-stone-900 mb-6">Register</h1>

      {formError && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {formError}
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
          {fieldErrors.email && (
            <p className="mt-1 text-xs text-red-600">{fieldErrors.email}</p>
          )}
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
          {fieldErrors.password && (
            <p className="mt-1 text-xs text-red-600">{fieldErrors.password}</p>
          )}
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            Name (optional)
          </span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            Phone (optional)
          </span>
          <input
            type="text"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            Address (optional)
          </span>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {submitting ? "Registering..." : "Register"}
        </button>
      </form>

      <p className="mt-4 text-sm text-stone-500">
        Already have an account?{" "}
        <Link
          href={returnTo ? `/login?returnTo=${encodeURIComponent(returnTo)}` : "/login"}
          className="font-medium text-stone-900 underline"
        >
          Log in
        </Link>
      </p>
    </div>
  );
}