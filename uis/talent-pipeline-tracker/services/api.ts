// All network access lives here. Components never call fetch directly —
// they call these functions. Every call is async/await and throws a clear
// Error on failure so the UI can show an error state.

import {
  Candidate,
  CandidateListResponse,
  CandidateCreateInput,
  CandidateUpdateInput,
  CandidateStatus,
  CandidateStage,
  Note,
} from "@/types/candidate";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL;

// Shared helper: runs a fetch, checks the response, parses JSON.
// Throws a readable Error if the request fails, so callers can catch it.
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  if (!BASE_URL) {
    throw new Error("API URL is not configured. Check .env.local.");
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed (${response.status}). Please try again.`);
  }

  // DELETE endpoints may return an empty body — guard against that.
  const text = await response.text();
  return (text ? JSON.parse(text) : null) as T;
}

// --- Candidates ---

export async function getCandidates(): Promise<CandidateListResponse> {
  // limit is set high so the full candidate set — including newly created
  // records beyond the first page — is fetched in one call.
  return request<CandidateListResponse>("/records?limit=1000");
}

export async function getCandidate(id: string): Promise<Candidate> {
  return request<Candidate>(`/records/${id}`);
}

export async function createCandidate(input: CandidateCreateInput): Promise<Candidate> {
  return request<Candidate>("/records", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateCandidate(
  id: string,
  input: CandidateUpdateInput
): Promise<Candidate> {
  return request<Candidate>(`/records/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function patchStatus(id: string, status: CandidateStatus): Promise<Candidate> {
  return request<Candidate>(`/records/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function patchStage(id: string, stage: CandidateStage): Promise<Candidate> {
  return request<Candidate>(`/records/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ stage }),
  });
}

// --- Notes ---

export async function getNotes(id: string): Promise<Note[]> {
  return request<Note[]>(`/records/${id}/notes`);
}

export async function addNote(id: string, content: string): Promise<Note> {
  return request<Note>(`/records/${id}/notes`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function deleteNote(id: string, noteId: string): Promise<void> {
  await request<null>(`/records/${id}/notes/${noteId}`, {
    method: "DELETE",
  });
}