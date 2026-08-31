// lib/api.ts
//
// All network access lives here — pages call these functions, never
// fetch() directly. This mirrors the convention already used in the
// incidents and talent-pipeline-tracker apps.

import { clearToken, getToken } from "./auth";
import { track } from "./telemetry";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

// Wraps fetch for any call that needs a valid session: reads the token,
// attaches it as `Authorization: Bearer <token>`, and — if the backend
// comes back with 401 — clears the token and sends the browser to
// /login. That 401 handling is what AUTH-02 means by "if a protected
// API call returns 401, clear the session and redirect": it happens
// here once, for every caller, instead of being repeated in every page.
//
// Also the one place every protected call passes through, which makes
// it the right spot for two cross-cutting telemetry events (technical
// baseline, per the telemetry unit): api_latency_recorded on every
// call, and user_login_failed(session_expired) exactly where an
// expired/invalid token is detected and the user gets bounced back to
// /login.
export async function authFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const startedAt = performance.now();
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  track("api_latency_recorded", {
    endpoint: path,
    duration_ms: Math.round(performance.now() - startedAt),
    status_code: response.status,
  });

  if (response.status === 401) {
    track("user_login_failed", { failure_reason: "session_expired" });
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

  // This call happens before a session exists, so it goes through raw
  // fetch (not authFetch) and is instrumented here directly rather than
  // relying on authFetch's api_latency_recorded/session_expired hooks.
  const requestId = crypto.randomUUID();

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
  } catch {
    track("user_login_failed", { failure_reason: "network_error" }, requestId);
    throw new Error("Could not reach the server. Check your connection and try again.");
  }

  if (!res.ok) {
    track("user_login_failed", { failure_reason: "invalid_credentials" }, requestId);
    throw new Error("Incorrect email or password.");
  }
  const data = await res.json();
  track("user_login_succeeded", {}, requestId);
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


// --- Password reset and change (AUTH-03) ---

export async function forgotPassword(email: string): Promise<void> {
  // The backend always returns 200 here, whether or not the email is
  // registered -- so this only throws on a genuine network failure,
  // never based on the response body. The page calling this shows the
  // same generic message either way, on purpose.
  const requestId = crypto.randomUUID();
  const res = await fetch(`${API_BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    throw new Error("Could not process request. Please try again.");
  }
  // Fired on any 200 -- the backend always returns 200 whether or not
  // the email is registered (see the comment above), so this counts
  // "someone asked to reset a password," not "a real account exists."
  track("password_reset_requested", {}, requestId);
}

export async function resetPassword(
  token: string,
  newPassword: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "That reset link is invalid or has expired."
    );
  }
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  const res = await authFetch("/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : "Could not change your password."
    );
  }
  track("password_changed");
}