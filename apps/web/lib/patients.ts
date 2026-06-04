import { apiFetch } from "@/lib/api";

export interface PatientListItem {
  id: string;
  first_name: string;
  last_name: string;
  mrn: string | null;
  city: string | null;
  state: string | null;
  created_at: string;
}

export interface PatientListResponse {
  items: PatientListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface PatientDetail {
  id: string;
  first_name: string;
  last_name: string;
  dob: string;
  phone: string;
  email: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  mrn: string | null;
  created_at: string;
}

export async function listPatients(q?: string): Promise<PatientListResponse> {
  const qs = q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  const resp = await apiFetch(`/api/patients/${qs}`);
  if (!resp.ok) return { items: [], total: 0, limit: 0, offset: 0 };
  return (await resp.json()) as PatientListResponse;
}

export async function getPatient(id: string): Promise<PatientDetail | null> {
  const resp = await apiFetch(`/api/patients/${id}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`patient detail fetch failed: ${resp.status}`);
  return (await resp.json()) as PatientDetail;
}
