"use client";

import { CandidateCreateInput, CandidateStatus, CandidateStage } from "@/types/candidate";
import { STATUS_OPTIONS, STAGE_OPTIONS } from "@/lib/labels";

// Reusable set of candidate form fields, shared by the register and edit pages.
// The parent owns the state; this component just renders inputs and reports changes.

interface CandidateFormFieldsProps {
  values: CandidateCreateInput;
  errors: Partial<Record<keyof CandidateCreateInput, string>>;
  onChange: (field: keyof CandidateCreateInput, value: string | number | null) => void;
}

export default function CandidateFormFields({ values, errors, onChange }: CandidateFormFieldsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Full name" error={errors.full_name} required>
        <input
          type="text"
          value={values.full_name}
          onChange={(e) => onChange("full_name", e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="Email" error={errors.email} required>
        <input
          type="email"
          value={values.email}
          onChange={(e) => onChange("email", e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="Phone" error={errors.phone} required>
        <input
          type="tel"
          value={values.phone}
          onChange={(e) => onChange("phone", e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="Position" error={errors.position} required>
        <input
          type="text"
          value={values.position}
          onChange={(e) => onChange("position", e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="LinkedIn URL" error={errors.linkedin_url}>
        <input
          type="url"
          value={values.linkedin_url ?? ""}
          onChange={(e) => onChange("linkedin_url", e.target.value || null)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="CV URL" error={errors.cv_url}>
        <input
          type="url"
          value={values.cv_url ?? ""}
          onChange={(e) => onChange("cv_url", e.target.value || null)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="Years of experience" error={errors.experience_years} required>
        <input
          type="number"
          min={0}
          value={values.experience_years}
          onChange={(e) => onChange("experience_years", Number(e.target.value))}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
      </Field>

      <Field label="Status" error={errors.status} required>
        <select
          value={values.status}
          onChange={(e) => onChange("status", e.target.value as CandidateStatus)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Stage" error={errors.stage} required>
        <select
          value={values.stage}
          onChange={(e) => onChange("stage", e.target.value as CandidateStage)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        >
          {STAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
}

// Small labeled wrapper with an inline error message.
function Field({
  label,
  error,
  required,
  children,
}: {
  label: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-gray-700">
        {label} {required && <span className="text-red-500">*</span>}
      </span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}