import { CandidateStatus, CandidateStage } from "@/types/candidate";

export function statusTone(status: CandidateStatus): "neutral" | "blue" | "green" | "red" | "amber" {
  switch (status) {
    case "received":
      return "neutral";
    case "in_progress":
      return "blue";
    case "selected":
      return "green";
    case "discarded":
      return "red";
    default:
      return "neutral";
  }
}

export function stageTone(): "amber" {
  // Stages share one tone to keep status the primary color signal.
  return "amber";
}