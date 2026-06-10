"use client";

import { useActiveClinicId } from "@/components/providers/clinic-provider";
import type { Task, TaskListResponse, TaskPriority, TaskStatus } from "@/lib/types/workflow";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  const clinicId = useActiveClinicId();
  const params = filtersToParams(filters);
  const qs = params.toString();
  return useQuery<TaskListResponse>({
    queryKey: ["tasks", clinicId, filters],
    queryFn: async () => {
      const r = await fetch(`/api/v1/tasks${qs ? `?${qs}` : ""}`);
      if (!r.ok) throw new Error(`GET /tasks failed: ${r.status}`);
      return r.json();
    },
  });
}

export interface TaskPatch {
  status?: Task["status"];
  assigned_to?: string | null;
  priority?: Task["priority"];
  description?: string | null;
}

export function useTaskMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { id: string; patch: TaskPatch }) => {
      const r = await fetch(`/api/v1/tasks/${payload.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload.patch),
      });
      if (!r.ok) {
        throw new Error(`PATCH /tasks/${payload.id} failed: ${r.status}`);
      }
      return (await r.json()) as Task;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}
