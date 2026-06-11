"use client";

import { useActiveClinicId } from "@/components/providers/clinic-provider";
import { useQuery } from "@tanstack/react-query";

export type OutreachChannel = "sms" | "email" | "voice";
export type OutreachStatus =
  | "pending"
  | "sent"
  | "delivered"
  | "responded"
  | "no_response"
  | "failed";

export interface OutreachAttempt {
  id: string;
  patient_id: string;
  referral_id: string | null;
  discharge_summary_id: string | null;
  channel: OutreachChannel;
  status: OutreachStatus;
  scheduled_at: string;
  sent_at: string | null;
  outcome: Record<string, unknown>;
  attempt_number: number;
  scheduling_link_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface OutreachAttemptListResponse {
  items: OutreachAttempt[];
}

export function useOutreachList(opts?: {
  channel?: OutreachChannel;
  status?: OutreachStatus;
}) {
  const clinicId = useActiveClinicId();
  const params = new URLSearchParams();
  if (opts?.channel) params.set("channel", opts.channel);
  if (opts?.status) params.set("status", opts.status);
  const qs = params.toString();
  return useQuery<OutreachAttemptListResponse>({
    queryKey: ["outreach", "list", clinicId, opts ?? {}],
    queryFn: async () => {
      const r = await fetch(`/api/v1/outreach${qs ? `?${qs}` : ""}`);
      if (!r.ok) throw new Error(`outreach list failed: ${r.status}`);
      return r.json();
    },
  });
}

export function usePatientOutreachHistory(patientId: string) {
  const clinicId = useActiveClinicId();
  return useQuery<OutreachAttemptListResponse>({
    queryKey: ["outreach", "patient", clinicId, patientId],
    queryFn: async () => {
      const r = await fetch(`/api/v1/outreach/patient/${patientId}`);
      if (!r.ok) throw new Error(`patient outreach failed: ${r.status}`);
      return r.json();
    },
    enabled: !!patientId,
  });
}
