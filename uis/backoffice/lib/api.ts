// lib/api.ts
//
// All network access lives here — pages call these functions, never
// fetch() directly. This mirrors the convention already used in the
// incidents and talent-pipeline-tracker apps.

import { clearToken, getToken } from "./auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

// Wraps fetch for any call that needs a valid session: reads the token,
// attaches it as `Authorization: Bearer <token>`, and — if the backend
// comes back with 401 — clears the token and sends the browser to
// /login. That 401 handling is what AUTH-02 means by "if a protected
// API call returns 401, clear the session and redirect": it happens
// here once, for every caller, instead of being repeated in every page.
export async function authFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  return response;
}

// --- Auth ---

export type Role = "admin" | "manager" | "user";

export type Profile = {
  id: number;
  user_id: number;
  name: string | null;
  phone: string | null;
  address: string | null;
};

export type MeResponse = {
  email: string;
  role: Role;
  profile: Profile;
};

export async function login(email: string, password: string): Promise<string> {
  // /auth/login expects OAuth2's standard form fields, not JSON -- the
  // form only has a "username" field, which we fill with the email.
  // See services/api/routes/auth.py for why: this is what lets FastAPI's
  // /docs "Authorize" button work, and the frontend has to speak the
  // same protocol.
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!res.ok) {
    throw new Error("Incorrect email or password.");
  }
  const data = await res.json();
  return data.access_token as string;
}

export async function registerUser(input: {
  email: string;
  password: string;
  name?: string;
  phone?: string;
  address?: string;
}): Promise<void> {
  const res = await fetch(`${API_BASE}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : "Could not register."
    );
  }
}

export async function getMe(): Promise<MeResponse> {
  const res = await authFetch("/auth/me");
  if (!res.ok) throw new Error(`Could not load your account (${res.status}).`);
  return res.json();
}

export async function updateProfile(changes: {
  name?: string;
  phone?: string;
  address?: string;
}): Promise<Profile> {
  const res = await authFetch("/profiles/me", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw new Error(`Could not update your profile (${res.status}).`);
  return res.json();
}