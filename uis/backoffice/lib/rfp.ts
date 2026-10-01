// lib/rfp.ts
//
// Every call to /rfp/* lives here -- the RFP page imports these functions
// and never calls fetch() or authFetch() directly. Same pattern as
// lib/inventory.ts, built on authFetch() in lib/api.ts (login token and
// 401 handling already happen there).
//
// The types mirror what services/api/routes/rfp.py sends back.

import { authFetch } from "./api";

// Part 1 statuses, then the Part 2 ones (drafting, under_evaluation, needs_human_review).
export type TicketStatus =
  | "analyzing"
  | "intake_complete"
  | "discarded"
  | "failed"
  | "drafting"
  | "under_evaluation"
  | "needs_human_review";

export type TicketListItem = {
  ticket_id: number;
  status: TicketStatus;
  original_filename: string;
  client_name: string | null;
  departments_needed: string[];
  generation_running: boolean;
  created_at: string;
  updated_at: string;
};

export type TicketMetadata = {
  client_name: string | null;
  location: string | null;
  service_type: string | null;
  scope: string | null;
  deadline: string | null;
  budget_range: string | null;
  language: string | null;
  departments_needed: string[];
  missing_fields: string[];
  word_count: number | null;
  flesch_kincaid: number | null;
  gunning_fog: number | null;
  readability_note: string | null;
};

export type SalesDepartment = {
  department_id: string;
  owner: string;
  key_aspects: string[];
  open_questions: string[];
};

export type SalesSummary = {
  overview: string;
  overview_source: string;
  departments: SalesDepartment[];
  missing_fields: string[];
  other_departments_mentioned: string[];
  total_open_questions: number;
};

// What the evaluators found about one draft (the EvaluationResult from the
// ticket), plus how the generate / evaluate loop went. While a department is
// still working, only section_status, stage and iteration are filled in.
export type RuleViolation = {
  rule_id: string;
  message: string;
  evidence: string;
};

export type SectionEvaluation = {
  section_status: "running" | "passed" | "needs_human_review";
  // while running
  stage?: string;
  iteration?: number;
  // once finished
  department_id?: string;
  iterations?: number;
  overall_pass?: boolean;
  readability?: { pass: boolean; score: number | null; details: string };
  relevance?: { pass: boolean; missing_aspects: string[] };
  compliance?: { pass: boolean; rule_ids: string[]; violations: RuleViolation[] };
  feedback_for_generator?: string;
  error?: string | null;
};

export type TicketSection = {
  department_id: string;
  key_aspects: string[];
  open_questions: string[];
  approval_status: string;
  draft_content: string | null;
  evaluation_results: SectionEvaluation | null;
};

export type TicketDetail = {
  ticket_id: number;
  status: TicketStatus;
  original_filename: string;
  rfp_id: string | null;
  discard_reason: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  metadata: TicketMetadata | null;
  sales_summary: SalesSummary | null;
  generation_running: boolean;
  average_iterations: number | null;
  sections: TicketSection[];
};

// Turns a failed response into a readable message. FastAPI puts the reason
// in body.detail, same as the other lib files.
async function failureMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : `${fallback} (${res.status}).`;
}

export async function uploadRfp(
  file: File
): Promise<{ ticket_id: number; status: TicketStatus }> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header on purpose: the browser adds it, with the
  // boundary value a file upload needs.
  const res = await authFetch("/rfp/tickets", { method: "POST", body: form });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not upload the RFP"));
  return res.json();
}

// Starts the draft proposal for a ticket that finished intake. The API answers
// at once (202); the drafts are written in the background, and the ticket's
// status and each department's row show the progress while the page polls.
export async function generateDrafts(
  ticketId: number
): Promise<{ ticket_id: number; status: TicketStatus }> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/generate`, { method: "POST" });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not start the drafts"));
  return res.json();
}

export async function listTickets(): Promise<TicketListItem[]> {
  const res = await authFetch("/rfp/tickets");
  if (!res.ok) throw new Error(await failureMessage(res, "Could not load the tickets"));
  return res.json();
}

export async function getTicket(ticketId: number): Promise<TicketDetail> {
  const res = await authFetch(`/rfp/tickets/${ticketId}`);
  if (!res.ok) throw new Error(await failureMessage(res, "Could not load that ticket"));
  return res.json();
}
