"use client";

import { Calendar, Edit2, Eye, MessageCircle, Plus, Trash2 } from "lucide-react";

import { ChannelIcon } from "@/components/outreach/channel-icon";
import type { TimelineEvent } from "@/lib/queries/timeline";
import { useReferralTimeline } from "@/lib/queries/timeline";

type IconType = React.ComponentType<{ className?: string }>;

const ACTION_LABEL: Record<string, { label: string; icon: IconType }> = {
  create: { label: "Created", icon: Plus },
  update: { label: "Updated", icon: Edit2 },
  delete: { label: "Deleted", icon: Trash2 },
  view: { label: "Viewed", icon: Eye },
  outreach_pending: { label: "Outreach scheduled", icon: Calendar },
  outreach_sent: { label: "Outreach sent", icon: MessageCircle },
  outreach_delivered: { label: "Outreach delivered", icon: MessageCircle },
  outreach_responded: { label: "Patient responded", icon: MessageCircle },
  outreach_no_response: { label: "No response yet", icon: MessageCircle },
  outreach_failed: { label: "Outreach failed", icon: MessageCircle },
};

function renderAction(e: TimelineEvent): React.ReactNode {
  const cfg = ACTION_LABEL[e.action];
  const Icon = cfg?.icon;
  const isOutreach = e.resource_type === "outreach_attempts";
  const channel = e.metadata?.channel;
  return (
    <span className="inline-flex items-center gap-2">
      {Icon ? <Icon className="h-3.5 w-3.5 text-muted-foreground" /> : null}
      <span>
        {cfg?.label ?? `${e.action} on ${e.resource_type}`}
        {isOutreach && channel ? (
          <span className="ml-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
            <ChannelIcon channel={channel} className="h-3 w-3" />
            <span className="uppercase">{channel}</span>
            {e.metadata?.attempt_number && e.metadata.attempt_number > 1 ? (
              <span>· try {e.metadata.attempt_number}</span>
            ) : null}
            {e.metadata?.scheduling_link_clicked ? (
              <span className="text-emerald-700">· clicked</span>
            ) : null}
            {e.metadata?.backfill_offered ? (
              <span className="text-blue-700">· backfill</span>
            ) : null}
          </span>
        ) : null}
      </span>
    </span>
  );
}

export function ReferralTimeline({ referralId }: { referralId: string }): React.ReactElement {
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
    <ol className="relative ml-4 border-l border-muted-foreground/30">
      {events.map((e, i) => (
        <li key={`${e.at}-${i}`} className="mb-6 ml-4">
          <span className="absolute -left-2 mt-1.5 h-3 w-3 rounded-full bg-primary" />
          <time className="text-xs text-muted-foreground">{new Date(e.at).toLocaleString()}</time>
          <p className="text-sm font-medium">{renderAction(e)}</p>
          {e.changed_columns.length > 0 && (
            <p className="text-xs text-muted-foreground">changed: {e.changed_columns.join(", ")}</p>
          )}
        </li>
      ))}
    </ol>
  );
}
