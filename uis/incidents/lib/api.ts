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
