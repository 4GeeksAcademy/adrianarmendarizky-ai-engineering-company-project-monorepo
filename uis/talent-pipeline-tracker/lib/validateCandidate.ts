import { CandidateCreateInput } from "@/types/candidate";

// Validates the candidate form. Returns an errors object keyed by field.
// Empty object means valid. Mirrors the required fields the API expects.

export type CandidateErrors = Partial<Record<keyof CandidateCreateInput, string>>;

export function validateCandidateForm(values: CandidateCreateInput): CandidateErrors {
  const errors: CandidateErrors = {};

  if (!values.full_name.trim()) {
    errors.full_name = "Full name is required.";
  }

  if (!values.email.trim()) {
    errors.email = "Email is required.";
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) {
    errors.email = "Enter a valid email address.";
  }

  if (!values.phone.trim()) {
    errors.phone = "Phone is required.";
  }

  if (!values.position.trim()) {
    errors.position = "Position is required.";
  }

  if (values.experience_years < 0 || Number.isNaN(values.experience_years)) {
    errors.experience_years = "Years of experience must be 0 or more.";
  }

  return errors;
}