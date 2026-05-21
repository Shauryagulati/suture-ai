"use client";

import { useQuery } from "@tanstack/react-query";

export interface TimelineEvent {
  at: string;
  actor_id: string | null;
  action: "create" | "update" | "delete" | "view" | string;
  resource_type: string;
  resource_id: string;
  changed_columns: string[];
}

export interface TimelineResponse {
  events: TimelineEvent[];
}

export function useReferralTimeline(referralId: string) {
  return useQuery<TimelineResponse>({
    queryKey: ["timeline", "referral", referralId],
    queryFn: async () => {
      const r = await fetch(`/api/v1/referrals/${referralId}/timeline`);
      if (!r.ok) {
        throw new Error(`timeline fetch failed: ${r.status}`);
      }
      return r.json();
    },
    enabled: !!referralId,
  });
}
