import { apiFetch } from "@/lib/api";
import type { EvalCompareResponse, EvalRunDetail, EvalRunListResponse } from "@/lib/eval-types";

export async function listEvalRuns(): Promise<EvalRunListResponse> {
  const res = await apiFetch("/api/evals/");
  if (!res.ok) {
    throw new Error(`listEvalRuns failed: ${res.status}`);
  }
  return (await res.json()) as EvalRunListResponse;
}

export async function getEvalRun(id: string): Promise<EvalRunDetail> {
  const res = await apiFetch(`/api/evals/${id}`);
  if (!res.ok) {
    throw new Error(`getEvalRun failed: ${res.status}`);
  }
  return (await res.json()) as EvalRunDetail;
}

export async function compareEvalRuns(runA: string, runB: string): Promise<EvalCompareResponse> {
  const res = await apiFetch(`/api/evals/compare?run_a=${runA}&run_b=${runB}`);
  if (!res.ok) {
    throw new Error(`compareEvalRuns failed: ${res.status}`);
  }
  return (await res.json()) as EvalCompareResponse;
}
