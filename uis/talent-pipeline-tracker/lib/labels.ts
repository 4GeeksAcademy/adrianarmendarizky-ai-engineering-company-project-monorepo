// Human-readable labels for status and stage.
// The context is explicit: raw API values (in_progress, personal_interview, ...)
// must NEVER appear in the UI. Everything user-facing goes through these maps.

import { CandidateStatus, CandidateStage } from "@/types/candidate";

export const STATUS_LABELS: Record<CandidateStatus, string> = {
  received: "Received",
  in_progress: "In progress",
  selected: "Selected",
  discarded: "Discarded",
};

export const STAGE_LABELS: Record<CandidateStage, string> = {
  pending: "Pending review",
  review: "Under review",
  personal_interview: "Personal interview",
  technical_interview: "Technical interview",
  offer_presented: "Offer presented",
};

// Ordered lists for dropdowns / filters (value + label pairs).
export const STATUS_OPTIONS: { value: CandidateStatus; label: string }[] = [
  { value: "received", label: STATUS_LABELS.received },
  { value: "in_progress", label: STATUS_LABELS.in_progress },
  { value: "selected", label: STATUS_LABELS.selected },
  { value: "discarded", label: STATUS_LABELS.discarded },
];

export const STAGE_OPTIONS: { value: CandidateStage; label: string }[] = [
  { value: "pending", label: STAGE_LABELS.pending },
  { value: "review", label: STAGE_LABELS.review },
  { value: "personal_interview", label: STAGE_LABELS.personal_interview },
  { value: "technical_interview", label: STAGE_LABELS.technical_interview },
  { value: "offer_presented", label: STAGE_LABELS.offer_presented },
];

// Safe lookups — fall back to the raw value only if an unknown value slips in,
// so the UI never crashes on unexpected data.
export function statusLabel(value: CandidateStatus): string {
  return STATUS_LABELS[value] ?? value;
}

export function stageLabel(value: CandidateStage): string {
  return STAGE_LABELS[value] ?? value;
}