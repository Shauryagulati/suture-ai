import { apiFetch } from "@/lib/api";
import type { OutreachChannel } from "@/lib/queries/outreach";

export interface OutreachDashboardRow {
  id: string;
  channel: OutreachChannel;
  status: string;
  scheduled_at: string;
  sent_at: string | null;
  attempt_number: number;
  patient_first_name: string;
  patient_last_name: string;
  related_type: string | null;
  message_subject: string | null;
  message_body: string;
}

export async function getOutreachDashboard(): Promise<OutreachDashboardRow[]> {
  const resp = await apiFetch("/api/outreach/dashboard");
  if (!resp.ok) return [];
  const data = (await resp.json()) as { items: OutreachDashboardRow[] };
  return data.items ?? [];
}
