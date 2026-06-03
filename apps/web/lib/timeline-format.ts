// Human-readable labels for audit-derived timeline events. The backend emits
// raw verbs ("create", "update", "view") and table names ("discharge_summaries",
// "referral_tasks"); these map them to clinic-facing language.

const ACTION_LABELS: Record<string, string> = {
  create: "Created",
  update: "Updated",
  delete: "Deleted",
  view: "Viewed",
};

const RESOURCE_LABELS: Record<string, string> = {
  referrals: "Referral",
  referral_tasks: "Task",
  discharge_summaries: "Discharge Summary",
  outreach_attempts: "Outreach",
  documents: "Document",
  document_extractions: "Extraction",
  patients: "Patient",
  appointments: "Appointment",
  prior_auths: "Prior Auth",
  insurance_policies: "Insurance Policy",
  calls: "Call",
};

function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatTimelineAction(action: string): string {
  return ACTION_LABELS[action] ?? titleCase(action);
}

export function formatResourceType(resourceType: string): string {
  return RESOURCE_LABELS[resourceType] ?? titleCase(resourceType);
}
