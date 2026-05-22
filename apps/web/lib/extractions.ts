import { apiFetch } from "@/lib/api";
import type {
  ExtractionDetail,
  ExtractionListResponse,
  ExtractionPatchBody,
} from "@/lib/extraction-types";

export interface ExtractionListFilters {
  needs_review?: boolean;
  limit?: number;
  offset?: number;
}

function toQuery(filters: ExtractionListFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function listExtractions(
  filters: ExtractionListFilters = {},
): Promise<ExtractionListResponse> {
  const res = await apiFetch(`/api/extractions/${toQuery(filters)}`);
  if (!res.ok) {
    throw new Error(`listExtractions failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as ExtractionListResponse;
}

export async function getExtraction(id: string): Promise<ExtractionDetail> {
  const res = await apiFetch(`/api/extractions/${id}`);
  if (!res.ok) {
    throw new Error(`getExtraction failed: ${res.status}`);
  }
  return (await res.json()) as ExtractionDetail;
}

export async function patchExtractionField(
  id: string,
  body: ExtractionPatchBody,
): Promise<ExtractionDetail> {
  const res = await apiFetch(`/api/extractions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`patchExtraction failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as ExtractionDetail;
}

export async function findExtractionForDocument(
  documentId: string,
): Promise<ExtractionDetail | null> {
  // Linear scan via the list endpoint. For v1 the per-doc set is small.
  const list = await listExtractions({ limit: 200 });
  const match = list.items.find((item) => item.document_id === documentId);
  if (!match) return null;
  return getExtraction(match.id);
}
