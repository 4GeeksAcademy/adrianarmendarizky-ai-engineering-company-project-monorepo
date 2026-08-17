"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { getMe, updateProfile, type MeResponse } from "@/lib/api";

export default function AccountProfilePage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function loadProfile() {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getMe();
      setMe(data);
      setName(data.profile.name ?? "");
      setPhone(data.profile.phone ?? "");
      setAddress(data.profile.address ?? "");
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load your account."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProfile();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setSaved(false);
    setSaving(true);
    try {
      const updatedProfile = await updateProfile({ name, phone, address });
      setMe((prev) => (prev ? { ...prev, profile: updatedProfile } : prev));
      setSaved(true);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Could not save changes."
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-stone-500">Loading your account...</p>;
  }

  if (loadError || !me) {
    return (
      <div className="space-y-3">
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {loadError ?? "Could not load your account."}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadProfile}
            className="rounded border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
          >
            Retry
          </button>
          <Link href="/" className="text-sm text-stone-600 underline hover:text-stone-800">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">My account</h1>
        <p className="text-sm text-stone-500 mt-1">
          {me.email} · {me.role}
        </p>
        <Link
          href="/account/change-password"
          className="text-sm text-stone-500 underline hover:text-stone-700"
        >
          Change password
        </Link>
      </div>

      {saveError && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {saveError}
        </p>
      )}
      {saved && (
        <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">
          Saved.
        </p>
      )}

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-stone-200 bg-white p-5 shadow-sm"
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">Name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">Phone</span>
          <input
            type="text"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-stone-700">
            Address
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
          disabled={saving}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save changes"}
        </button>
      </form>
    </div>
  );
}