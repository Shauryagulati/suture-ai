import type { DashboardPayload, LeakageSummary, RoiReport } from "@/lib/analytics-types";
import { apiFetch } from "@/lib/api";

export async function getDashboard(): Promise<DashboardPayload> {
  const r = await apiFetch("/api/analytics/dashboard");
  if (!r.ok) throw new Error(`GET /api/analytics/dashboard failed: ${r.status}`);
  return r.json();
}

export async function getLeakage(): Promise<LeakageSummary> {
  const r = await apiFetch("/api/analytics/leakage");
  if (!r.ok) throw new Error(`GET /api/analytics/leakage failed: ${r.status}`);
  return r.json();
}

export async function getRoi(from?: string, to?: string): Promise<RoiReport> {
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  const path = `/api/analytics/roi${qs.toString() ? `?${qs}` : ""}`;
  const r = await apiFetch(path);
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return r.json();
}
