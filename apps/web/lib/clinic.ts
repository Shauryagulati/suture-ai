import { apiFetch } from "@/lib/api";

export interface ClinicMember {
  email: string;
  full_name: string;
  role: string;
}

export interface ClinicSettings {
  clinic_id: string;
  clinic_name: string;
  your_role: string;
  members: ClinicMember[];
}

export async function getClinicSettings(): Promise<ClinicSettings | null> {
  const resp = await apiFetch("/api/clinic/settings");
  if (!resp.ok) return null;
  return (await resp.json()) as ClinicSettings;
}
