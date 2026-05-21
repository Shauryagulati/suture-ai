"use client";

import type { TaskListResponse, TaskPriority, TaskStatus } from "@/lib/types/workflow";
import { useQuery } from "@tanstack/react-query";

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  overdue?: boolean;
  assignee?: string;
}

function filtersToParams(filters: TaskFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.overdue) params.set("overdue", "true");
  if (filters.assignee) params.set("assignee", filters.assignee);
  return params;
}

export function useTasksQuery(filters: TaskFilters) {
  const params = filtersToParams(filters);
  const qs = params.toString();
  return useQuery<TaskListResponse>({
    queryKey: ["tasks", filters],
    queryFn: async () => {
      const r = await fetch(`/api/v1/tasks${qs ? `?${qs}` : ""}`);
      if (!r.ok) throw new Error(`GET /tasks failed: ${r.status}`);
      return r.json();
    },
  });
}
