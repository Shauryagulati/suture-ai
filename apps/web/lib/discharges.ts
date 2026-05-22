import { apiFetch } from "@/lib/api";

export type DischargeStatus =
  | "new"
  | "patient_contacted"
  | "scheduled"
  | "seen"
  | "confirmation_sent"
  | "at_risk";

export type UrgencyTier = "critical" | "high" | "medium" | "routine";

export type Discharge = {
  id: string;
  patient_id: string;
  patient_first_name: string;
  patient_last_name: string;
  status: DischargeStatus;
  urgency_tier: UrgencyTier;
  discharge_date: string;
  primary_diagnosis: string | null;
  diagnosis_codes: string[];
  urgent_flags: string[];
  follow_up_window_days: number | null;
  follow_up_deadline: string | null;
  recommended_specialist: string | null;
  confirmation_fax_sent_at: string | null;
  confirmation_fax_path: string | null;
};

export type TimelineEvent = {
  at: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  changed_columns: string[];
  metadata: Record<string, unknown>;
};

export type Timeline = { events: TimelineEvent[] };

export async function getDischarge(id: string): Promise<Discharge> {
  const r = await apiFetch(`/api/discharges/${id}`, { cache: "no-store" });
  if (!r.ok) {
    throw new Error(`getDischarge ${id}: ${r.status} ${await r.text()}`);
  }
  return (await r.json()) as Discharge;
}

export async function getDischargeTimeline(id: string): Promise<Timeline> {
  const r = await apiFetch(`/api/discharges/${id}/timeline`, { cache: "no-store" });
  if (!r.ok) {
    throw new Error(`getDischargeTimeline ${id}: ${r.status} ${await r.text()}`);
  }
  return (await r.json()) as Timeline;
}
