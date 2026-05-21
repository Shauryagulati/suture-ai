import { Badge } from "@/components/ui/badge";
import type { TaskStatus } from "@/lib/types/workflow";

export function SLABadge({
  dueAt,
  status,
}: {
  dueAt: string | null;
  status: TaskStatus;
}) {
  if (!dueAt || status === "completed" || status === "cancelled") {
    return <span className="text-muted-foreground text-xs">—</span>;
  }
  const due = new Date(dueAt);
  const now = new Date();
  const hrs = (due.getTime() - now.getTime()) / 3_600_000;
  if (hrs < 0) return <Badge className="bg-red-600 text-white">Overdue</Badge>;
  if (hrs < 24) return <Badge className="bg-amber-500 text-white">{"< 24h"}</Badge>;
  return <Badge className="bg-emerald-600 text-white">On track</Badge>;
}
