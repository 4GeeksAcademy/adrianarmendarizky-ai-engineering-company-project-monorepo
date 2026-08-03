// lib/api.ts
// Talks to the Brasaland Incidents API (services/api). Keeping the fetch
// calls here, separate from the page component, so the UI code only ever
// deals with data it already has, not with how it got here.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const response = await fetch(`${API_BASE_URL}/api/incidents/analyze`, {
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

export function getExportUrl(): string {
  return `${API_BASE_URL}/api/incidents/results/export`;
}
