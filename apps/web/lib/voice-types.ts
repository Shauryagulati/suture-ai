// Mirror of apps/api/app/schemas/voice.py.
// Update both ends in lockstep when adding fields.

export type CallStatus =
  | "initiated"
  | "in_progress"
  | "completed"
  | "failed"
  | "no_answer"
  | "voicemail";

export type CallType = "outbound_scheduling" | "outbound_followup" | "inbound";

export interface CallResponse {
  id: string;
  patient_id: string;
  outreach_attempt_id: string | null;
  call_type: CallType;
  status: CallStatus;
  duration_seconds: number | null;
  started_at: string;
  ended_at: string | null;
  outcome: Record<string, unknown>;
}

export interface CallListResponse {
  items: CallResponse[];
}

export interface CallTokenResponse {
  room_name: string;
  livekit_url: string;
  token: string;
  identity: string;
}

export interface TranscriptResponse {
  call_id: string;
  full_transcript: string;
  structured_data: Record<string, unknown>;
}

export interface StartCallResponse {
  call_id: string;
  room_name: string;
  redispatched: boolean;
}

export interface EndCallResponse {
  call_id: string;
  status: CallStatus;
  ended_at: string;
}

// WS payload — one of three shapes.
export type TranscriptStreamMessage =
  | { type: "turn"; role: "agent" | "patient"; text: string; ts: string }
  | { type: "state"; state: string }
  | { type: "end"; outcome: Record<string, unknown> };
