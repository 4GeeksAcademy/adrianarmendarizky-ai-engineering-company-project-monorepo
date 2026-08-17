// lib/incidentOptions.ts
//
// Value/label pairs for the Incident Manager's dropdowns. Branch values
// and display labels are copied verbatim from CONTEXT-brasaland.en
// (centralized).md -- the branch dropdown specifically has to show the
// readable name ("Medellín Centro"), never the internal value
// ("medellin_centro"). Category/status/origin don't have an explicit
// display-label table in CONTEXT, only internal values -- these labels
// are plain-language versions of those values.

export const BRANCHES = [
  { value: "central", label: "Central (Medellín / Miami)" },
  { value: "medellin_centro", label: "Medellín Centro" },
  { value: "medellin_laureles", label: "Medellín Laureles" },
  { value: "medellin_envigado", label: "Medellín Envigado" },
  { value: "medellin_bello", label: "Medellín Bello" },
  { value: "medellin_itagui", label: "Medellín Itagüí" },
  { value: "bogota_chapinero", label: "Bogotá Chapinero" },
  { value: "bogota_usaquen", label: "Bogotá Usaquén" },
  { value: "cali_granada", label: "Cali Granada" },
  { value: "barranquilla_norte", label: "Barranquilla Norte" },
  { value: "miami_doral", label: "Miami Doral" },
  { value: "miami_hialeah", label: "Miami Hialeah" },
  { value: "miami_kendall", label: "Miami Kendall" },
  { value: "orlando_international", label: "Orlando International Drive" },
  { value: "fort_lauderdale", label: "Fort Lauderdale" },
] as const;

export const CATEGORIES = [
  { value: "equipment_failure", label: "Equipment failure" },
  { value: "supply_issue", label: "Supply issue" },
  { value: "customer_complaint", label: "Customer complaint" },
  { value: "staff_issue", label: "Staff issue" },
  { value: "facility_issue", label: "Facility issue" },
  { value: "pos_system", label: "POS system" },
  { value: "delivery_issue", label: "Delivery issue" },
  { value: "other", label: "Other" },
] as const;

export const ORIGINS = [
  { value: "customer", label: "Customer" },
  { value: "branch", label: "Branch" },
  { value: "internal", label: "Internal" },
] as const;

export const STATUSES = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "discarded", label: "Discarded" },
] as const;

// The 4 valid transitions from CONTEXT, keyed by current status. An
// empty array means that status is final (resolved, discarded).
export const VALID_TRANSITIONS: Record<string, string[]> = {
  open: ["in_progress", "discarded"],
  in_progress: ["resolved", "discarded"],
  resolved: [],
  discarded: [],
};

function labelFor(options: readonly { value: string; label: string }[], value: string): string {
  return options.find((o) => o.value === value)?.label ?? value;
}

export const branchLabel = (value: string) => labelFor(BRANCHES, value);
export const categoryLabel = (value: string) => labelFor(CATEGORIES, value);
export const originLabel = (value: string) => labelFor(ORIGINS, value);
export const statusLabel = (value: string) => labelFor(STATUSES, value);
