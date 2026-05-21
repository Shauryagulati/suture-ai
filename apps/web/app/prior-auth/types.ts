export const PAYER_OPTIONS = [
  "Highmark BCBS PA",
  "UPMC Health Plan",
  "Aetna",
  "Cigna",
  "UnitedHealthcare",
] as const;

export const CPT_OPTIONS = [
  { code: "93015", label: "93015 — Treadmill stress test" },
  { code: "93306", label: "93306 — Transthoracic echo (TTE)" },
  { code: "93458", label: "93458 — Left heart catheterization" },
  { code: "93620", label: "93620 — EP study (comprehensive)" },
  { code: "93224", label: "93224 — 48-hour Holter monitor" },
] as const;

export type PolicyExcerpt = {
  payer_name: string;
  procedure_code: string;
  text: string;
  distance: number | null;
};

export type AuthDetermination = {
  auth_required: boolean;
  confidence: number;
  reasoning: string;
  required_documents: string[];
  typical_turnaround_days: number | null;
  relevant_policy_excerpts: PolicyExcerpt[];
  common_denial_reasons: string[];
};

export type PriorAuthRow = {
  id: string;
  clinic_id: string;
  referral_id: string | null;
  patient_id: string;
  payer_name: string;
  procedure_codes: string[];
  diagnosis_codes: string[];
  auth_required: boolean | null;
  status: PriorAuthStatus;
  submitted_at: string | null;
  approved_at: string | null;
  denied_at: string | null;
  follow_up_at: string | null;
  auth_number: string | null;
  packet_file_path: string | null;
  created_at: string;
  updated_at: string;
};

export type PriorAuthStatus =
  | "not_needed"
  | "checking"
  | "required"
  | "submitted"
  | "approved"
  | "denied"
  | "appealing"
  | "appeal_approved"
  | "appeal_denied";

export type PriorAuthEvent = {
  id: string;
  prior_auth_id: string;
  event_type: string;
  details: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
};

export type PriorAuthDetail = PriorAuthRow & {
  events: PriorAuthEvent[];
  auth_required_reasoning: string | null;
};
