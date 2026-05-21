import { Badge } from "@/components/ui/badge";
import type { TaskStatus } from "@/lib/types/workflow";

const TONE: Record<TaskStatus, string> = {
  pending: "bg-slate-100 text-slate-800 border-slate-200",
  in_progress: "bg-blue-100 text-blue-800 border-blue-200",
  completed: "bg-emerald-100 text-emerald-800 border-emerald-200",
  cancelled: "bg-zinc-100 text-zinc-600 border-zinc-200",
  overdue: "bg-red-100 text-red-800 border-red-200",
};

const LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
  overdue: "Overdue",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge variant="outline" className={TONE[status]}>
      {LABEL[status]}
    </Badge>
  );
}
