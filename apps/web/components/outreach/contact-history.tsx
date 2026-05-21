"use client";

import { ChannelIcon } from "@/components/outreach/channel-icon";
import { OutreachStatusBadge } from "@/components/outreach/status-badge";
import { usePatientOutreachHistory } from "@/lib/queries/outreach";

export function ContactHistory({
  patientId,
}: {
  patientId: string;
}): React.ReactElement {
  const { data, isLoading, error } = usePatientOutreachHistory(patientId);

  if (isLoading) {
    return <p className="text-muted-foreground text-sm">Loading contact history…</p>;
  }
  if (error) {
    return <p className="text-red-600 text-sm">Failed to load contact history.</p>;
  }
  const items = data?.items ?? [];
  if (items.length === 0) {
    return <p className="text-muted-foreground text-sm">No outreach attempts yet.</p>;
  }

  return (
    <ul className="space-y-3">
      {items.map((item) => {
        const outcome = item.outcome as Record<string, unknown>;
        const clicked = Boolean(outcome.scheduling_link_clicked);
        const backfill = Boolean(outcome.backfill_offered);
        return (
          <li
            key={item.id}
            className="flex items-start gap-3 rounded-lg border bg-card p-3"
          >
            <ChannelIcon channel={item.channel} className="mt-1 h-5 w-5" />
            <div className="flex-1">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium capitalize">{item.channel}</span>
                  <span className="text-xs text-muted-foreground">
                    {item.attempt_number > 1 ? `try ${item.attempt_number}` : ""}
                  </span>
                  {backfill ? (
                    <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
                      backfill
                    </span>
                  ) : null}
                  {clicked ? (
                    <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">
                      link clicked
                    </span>
                  ) : null}
                </div>
                <OutreachStatusBadge status={item.status} />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Scheduled {new Date(item.scheduled_at).toLocaleString()}
                {item.sent_at ? ` · Sent ${new Date(item.sent_at).toLocaleString()}` : ""}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
