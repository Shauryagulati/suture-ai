"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TaskFilters } from "@/lib/queries/tasks";
import type { TaskPriority, TaskStatus } from "@/lib/types/workflow";

const STATUSES: TaskStatus[] = ["pending", "in_progress", "completed", "cancelled", "overdue"];
const PRIORITIES: TaskPriority[] = ["critical", "high", "medium", "low"];

export function FilterBar({
  filters,
  onChange,
}: {
  filters: TaskFilters;
  onChange: (next: TaskFilters) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 py-2">
      <Select
        value={filters.status ?? "all"}
        onValueChange={(v) =>
          onChange({
            ...filters,
            status: v === "all" ? undefined : (v as TaskStatus),
          })
        }
      >
        <SelectTrigger className="w-44">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All statuses</SelectItem>
          {STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.priority ?? "all"}
        onValueChange={(v) =>
          onChange({
            ...filters,
            priority: v === "all" ? undefined : (v as TaskPriority),
          })
        }
      >
        <SelectTrigger className="w-44">
          <SelectValue placeholder="Priority" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All priorities</SelectItem>
          {PRIORITIES.map((p) => (
            <SelectItem key={p} value={p}>
              {p}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant={filters.overdue ? "default" : "outline"}
        onClick={() => onChange({ ...filters, overdue: !filters.overdue })}
      >
        Overdue only
      </Button>
    </div>
  );
}
