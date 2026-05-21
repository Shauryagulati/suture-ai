import { apiFetch } from "@/lib/api";
import type {
  DocumentDetail,
  DocumentListFilters,
  DocumentListResponse,
  DocumentPatchBody,
} from "@/lib/document-types";

function toQuery(filters: DocumentListFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function listDocuments(
  filters: DocumentListFilters = {},
): Promise<DocumentListResponse> {
  const res = await apiFetch(`/api/documents/${toQuery(filters)}`);
  if (!res.ok) {
    throw new Error(`listDocuments failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as DocumentListResponse;
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const res = await apiFetch(`/api/documents/${id}`);
  if (!res.ok) {
    throw new Error(`getDocument failed: ${res.status}`);
  }
  return (await res.json()) as DocumentDetail;
}

export async function patchDocument(id: string, body: DocumentPatchBody): Promise<DocumentDetail> {
  const res = await apiFetch(`/api/documents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`patchDocument failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as DocumentDetail;
}
