import { apiFetch } from "@/lib/api";
import type {
  CallListResponse,
  CallResponse,
  CallTokenResponse,
  EndCallResponse,
  StartCallResponse,
  StreamTokenResponse,
  TranscriptResponse,
} from "@/lib/voice-types";

export async function listActiveCalls(): Promise<CallListResponse> {
  const res = await apiFetch("/api/voice/calls/active");
  if (!res.ok) {
    throw new Error(`listActiveCalls failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as CallListResponse;
}

export async function getCallTranscript(callId: string): Promise<TranscriptResponse | null> {
  const res = await apiFetch(`/api/voice/calls/${callId}/transcript`);
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`getCallTranscript failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as TranscriptResponse;
}

export async function getCallToken(callId: string): Promise<CallTokenResponse> {
  const res = await apiFetch(`/api/voice/calls/${callId}/token`);
  if (!res.ok) {
    throw new Error(`getCallToken failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as CallTokenResponse;
}

export async function getStreamToken(callId: string): Promise<StreamTokenResponse> {
  // Server-side mint of a short-lived, call-scoped token for the transcript
  // WS. The FastAPI bearer stays on the server (it's the apiFetch auth); only
  // this scoped token reaches the client.
  const res = await apiFetch(`/api/voice/calls/${callId}/stream-token`);
  if (!res.ok) {
    throw new Error(`getStreamToken failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as StreamTokenResponse;
}

export async function startCall(callId: string): Promise<StartCallResponse> {
  const res = await apiFetch(`/api/voice/calls/${callId}/start`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`startCall failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as StartCallResponse;
}

export async function endCall(callId: string): Promise<EndCallResponse> {
  const res = await apiFetch(`/api/voice/calls/${callId}/end`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`endCall failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as EndCallResponse;
}

export async function getCallById(callId: string): Promise<CallResponse | null> {
  // No GET /calls/{id} on the API — derive from active list. Cheap enough
  // for v1; revisit when scale matters.
  const list = await listActiveCalls();
  return list.items.find((c) => c.id === callId) ?? null;
}
