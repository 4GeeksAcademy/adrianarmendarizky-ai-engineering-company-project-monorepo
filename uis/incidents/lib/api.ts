// lib/api.ts
// Talks to the Brasaland Incidents API (services/api). Keeping the fetch
// calls here, separate from the page component, so the UI code only ever
// deals with data it already has, not with how it got here.

import { clearToken, getBackofficeLoginUrl, getToken } from "./auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Every call in this file is protected, so every call goes through this
// instead of a plain fetch(): attaches the token, and -- on a 401 --
// clears it and sends the browser to Backoffice's /login.
async function authFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401) {
    clearToken();
    window.location.href = getBackofficeLoginUrl();
  }

  return response;
}

export type InvalidBreakdownItem = {
  rule: string;
  label: string;
  count: number;
};

export type CategoryBreakdownItem = {
  category: string;
  count: number;
  percentage: number;
};

export type StatusBreakdownItem = {
  status: string;
  count: number;
  percentage: number;
};

export type SatisfactionDistributionItem = {
  score: number;
  label: string;
  count: number;
};

export type AnalysisResult = {
  source_filename: string;
  total_records: number;
  valid_records: number;
  invalid_records: number;
  invalid_breakdown: InvalidBreakdownItem[];
  category_breakdown: CategoryBreakdownItem[];
  status_breakdown: StatusBreakdownItem[];
  satisfaction: {
    closed_total: number;
    scored_count: number;
    average_score: number;
    distribution: SatisfactionDistributionItem[];
  };
};

export class ApiError extends Error {}

// Thrown when the API's error response identifies a specific bad field
// (the shape routes/incidents.py returns for a 400: {field, message}) --
// lets a form show the message next to the right input instead of as a
// generic banner.
export class FieldValidationError extends ApiError {
  field: string;
  constructor(field: string, message: string) {
    super(message);
    this.field = field;
  }
}

async function throwForErrorResponse(response: Response): Promise<never> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (detail && typeof detail === "object" && "field" in detail && "message" in detail) {
    throw new FieldValidationError(detail.field, detail.message);
  }
  const message = typeof detail === "string" ? detail : `Request failed with status ${response.status}`;
  throw new ApiError(message);
}

// ---------------------------------------------------------------------------
// Centralized Incident Manager
// ---------------------------------------------------------------------------

export type Incident = {
  id: number;
  title: string;
  description: string;
  category: string;
  status: string;
  origin: string;
  branch: string;
  created_at: string;
  updated_at: string;
};

export type IncidentCreatePayload = {
  title: string;
  description: string;
  category: string;
  origin: string;
  branch: string;
};

export type IncidentSummary = {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_origin: Record<string, number>;
  by_branch: Record<string, number>;
};

export async function createIncident(payload: IncidentCreatePayload): Promise<Incident> {
  const response = await authFetch("/api/incidents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) return throwForErrorResponse(response);
  return response.json();
}

export async function listIncidents(
  filters: { status?: string; origin?: string; branch?: string; category?: string } = {}
): Promise<Incident[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  const response = await authFetch(`/api/incidents${query ? `?${query}` : ""}`);
  if (!response.ok) return throwForErrorResponse(response);
  return response.json();
}

export async function updateIncidentStatus(id: number, status: string): Promise<Incident> {
  const response = await authFetch(`/api/incidents/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) return throwForErrorResponse(response);
  return response.json();
}

export async function getIncidentSummary(): Promise<IncidentSummary> {
  const response = await authFetch("/api/incidents/summary");
  if (!response.ok) return throwForErrorResponse(response);
  return response.json();
}

export async function analyzeIncidentsFile(file: File): Promise<AnalysisResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await authFetch("/api/incidents/analyze", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.detail || `Request failed with status ${response.status}`
    );
  }

  return response.json();
}

// Was getExportUrl() -- returned a plain URL meant for an <a href>.
// That no longer works: /api/incidents/results/export is now a
// protected route, and a plain link click can't attach an
// Authorization header. This fetches the file with the token
// attached instead, then triggers the download itself.
export async function downloadResults(): Promise<void> {
  const response = await authFetch("/api/incidents/results/export");

  if (!response.ok) {
    throw new ApiError(`Could not download results (${response.status}).`);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "results.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
