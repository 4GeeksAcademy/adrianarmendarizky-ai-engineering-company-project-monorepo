// lib/rfp.ts
//
// Every call to /rfp/* lives here -- the RFP page imports these functions
// and never calls fetch() or authFetch() directly. Same pattern as
// lib/inventory.ts, built on authFetch() in lib/api.ts (login token and
// 401 handling already happen there).
//
// The types mirror what services/api/routes/rfp.py sends back.

import { authFetch } from "./api";

// Part 1 statuses, then the Part 2 ones (drafting, under_evaluation, needs_human_review),
// then the Part 3 ones (waiting_for_approval, done).
export type TicketStatus =
  | "analyzing"
  | "intake_complete"
  | "discarded"
  | "failed"
  | "drafting"
  | "under_evaluation"
  | "needs_human_review"
  | "waiting_for_approval"
  | "done";

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

// --- Part 3: approvals (Milestone 9) -----------------------------------------------------
//
// Mirror what services/api/routes/rfp_approval.py sends back. "subject" is the
// approver: a department id, or "ceo" when the estimated value is above $50,000 USD a year.

export type ApprovalStatus = "pending" | "approved" | "rejected";
export type ApprovalAction = "approve" | "reject" | "request_changes";

export type ApprovalEvaluation = {
  overall_pass?: boolean | null;
  readability?: { pass: boolean | null; score: number | null };
  relevance?: { pass: boolean | null; missing_aspects: string[] };
  compliance?: {
    pass: boolean | null;
    rule_ids: string[];
    violations: { rule_id?: string; message?: string; evidence?: string }[];
  };
};

export type ApproverCard = {
  key_aspects?: string[];
  open_questions?: string[];
  // only on the CEO's card
  estimated_annual_value_usd?: { low: number; high: number } | null;
  threshold_usd?: number;
  approved_sections?: { department_id: string; approver: string | null; approved_at: string | null }[];
};

export type Approver = {
  subject: string;
  approver: string | null;
  status: ApprovalStatus;
  waiting: boolean; // true while this approver's answer is being waited for
  acted_by: string | null;
  comments: string;
  estimates: Record<string, number>;
  decided_at: string | null;
  rejected_reason: string | null;
  revision_count: number;
  revisions_left: number;
  draft_content: string;
  evaluation: ApprovalEvaluation;
  card: ApproverCard;
};

export type Conflict = {
  trigger: string;
  arbiter: string;
  escalated_to: string | null;
  sections: string[];
  details: Record<string, unknown>;
  resolution: string;
  forced_action: string | null;
};

export type ArbitrationRequest = {
  trigger: string;
  arbiter: string;
  choices: string[];
  details: Record<string, unknown>;
  sections: string[];
};

export type Approvals = {
  ticket_id: number;
  status: TicketStatus;
  started: boolean;
  approvers: Approver[];
  arbitration: ArbitrationRequest | null;
  conflicts: Conflict[];
  warnings: string[];
  revision_limit: number;
  document_ready: boolean;
  message: string | null;
};

export type ApprovalOutcome = {
  outcome: string;
  pending: string[];
  waiting_for: string[];
  rejected: string[];
  blockers: string[];
  document_ready: boolean;
};

export type ApprovalAnswer = { outcome: ApprovalOutcome; approvals: Approvals };

export type DecisionBody = {
  action: ApprovalAction;
  comments?: string;
  estimates?: Record<string, number>;
};

export type FinalDocument = {
  ticket_id: number;
  sections: {
    department_id: string;
    title: string;
    content: string;
    approver: string | null;
    approved_at: string | null;
  }[];
  approvals: { subject: string; approver: string; acted_by: string | null; approved_at: string | null }[];
  total_estimated_value: {
    usd_low: number;
    usd_high: number;
    cop_low: number;
    cop_high: number;
    reference_rate_cop_per_usd: number;
    note: string;
  } | null;
  generated_at: string;
  markdown: string;
};

export type TraceEvent = {
  id: number;
  part: number;
  agent: string;
  event_type: string;
  subject: string | null;
  actor: string | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  created_at: string;
};

// Sends a ticket that has drafts to the department owners. The API answers when
// every approval is open (about a second), or after any forced rewrite.
export async function sendForApproval(ticketId: number): Promise<ApprovalAnswer> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/send-for-approval`, { method: "POST" });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not send the ticket for approval"));
  return res.json();
}

export async function getApprovals(ticketId: number): Promise<Approvals> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/approvals`);
  if (!res.ok) throw new Error(await failureMessage(res, "Could not load the approvals"));
  return res.json();
}

// One approver answers. Asking for changes rewrites the draft, which can take up to a minute.
export async function recordDecision(
  ticketId: number,
  subject: string,
  body: DecisionBody
): Promise<ApprovalAnswer> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/approvals/${subject}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not record the decision"));
  return res.json();
}

// Picks a rewrite up again after it was cut short (the model was unreachable).
export async function continueRewrite(ticketId: number, subject: string): Promise<ApprovalAnswer> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/approvals/${subject}/continue`, { method: "POST" });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not continue the rewrite"));
  return res.json();
}

// The named arbiter settles a cost-versus-feasibility conflict.
export async function answerArbitration(
  ticketId: number,
  trigger: string,
  body: { choice: string; comments: string }
): Promise<ApprovalAnswer> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/arbitration/${trigger}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await failureMessage(res, "Could not record the arbitration"));
  return res.json();
}

export async function getFinalDocument(ticketId: number): Promise<FinalDocument> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/final-document`);
  if (!res.ok) throw new Error(await failureMessage(res, "Could not load the final document"));
  return res.json();
}

export async function getTrace(ticketId: number): Promise<TraceEvent[]> {
  const res = await authFetch(`/rfp/tickets/${ticketId}/trace`);
  if (!res.ok) throw new Error(await failureMessage(res, "Could not load the trace"));
  return res.json();
}
