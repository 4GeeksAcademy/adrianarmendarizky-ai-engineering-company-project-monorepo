// Types matching the Brasaland Talent Pipeline Tracker API exactly.
// Field names mirror the API response (full_name, linkedin_url, etc.).

export type CandidateStatus = "received" | "in_progress" | "selected" | "discarded";

export type CandidateStage =
  | "pending"
  | "review"
  | "personal_interview"
  | "technical_interview"
  | "offer_presented";

export interface Note {
  id: string;
  record_id: string;
  content: string;
  created_at: string;
}

export interface Candidate {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  status: CandidateStatus;
  stage: CandidateStage;
  experience_years: number;
  applied_at: string;
  updated_at: string;
  notes: Note[];
  notes_count: number;
}

// The list endpoint wraps candidates in a paginated envelope.
export interface CandidateListResponse {
  total: number;
  page: number;
  limit: number;
  data: Candidate[];
}

// Payload for creating a candidate (POST) — the API generates id/dates.
export interface CandidateCreateInput {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  status: CandidateStatus;
  stage: CandidateStage;
  experience_years: number;
}

// Payload for editing a candidate (PUT).
export type CandidateUpdateInput = CandidateCreateInput;