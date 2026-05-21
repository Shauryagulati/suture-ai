import { Badge } from "@/components/ui/badge";

import type { OutreachStatus } from "@/lib/queries/outreach";

const STATUS_TONE: Record<OutreachStatus, string> = {
  pending: "bg-slate-100 text-slate-800 border-slate-200",
  sent: "bg-blue-100 text-blue-800 border-blue-200",
  delivered: "bg-emerald-100 text-emerald-800 border-emerald-200",
  responded: "bg-emerald-200 text-emerald-900 border-emerald-300",
  no_response: "bg-amber-100 text-amber-900 border-amber-200",
  failed: "bg-red-100 text-red-800 border-red-200",
};

const STATUS_LABEL: Record<OutreachStatus, string> = {
  pending: "Scheduled",
  sent: "Sent",
  delivered: "Delivered",
  responded: "Responded",
  no_response: "No response",
  failed: "Failed",
};

export function OutreachStatusBadge({
  status,
}: {
  status: OutreachStatus;
}): React.ReactElement {
  return (
    <Badge variant="outline" className={`border ${STATUS_TONE[status]}`}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}
