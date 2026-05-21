"use client";

import { useReferralTimeline } from "@/lib/queries/timeline";

export function ReferralTimeline({ referralId }: { referralId: string }) {
  const { data, isLoading, error } = useReferralTimeline(referralId);

  if (isLoading) {
    return <p className="text-muted-foreground text-sm">Loading timeline…</p>;
  }
  if (error) {
    return <p className="text-red-600 text-sm">Failed to load timeline.</p>;
  }
  const events = data?.events ?? [];
  if (events.length === 0) {
    return <p className="text-muted-foreground text-sm">No events yet.</p>;
  }

  return (
    <ol className="relative border-l border-muted-foreground/30 ml-4">
      {events.map((e, i) => (
        <li key={`${e.at}-${i}`} className="mb-6 ml-4">
          <span className="absolute -left-2 mt-1.5 h-3 w-3 rounded-full bg-primary" />
          <time className="text-xs text-muted-foreground">{new Date(e.at).toLocaleString()}</time>
          <p className="text-sm font-medium">
            {e.action} on {e.resource_type}
          </p>
          {e.changed_columns.length > 0 && (
            <p className="text-xs text-muted-foreground">changed: {e.changed_columns.join(", ")}</p>
          )}
        </li>
      ))}
    </ol>
  );
}
