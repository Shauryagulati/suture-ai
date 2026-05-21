"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useTaskMutation } from "@/lib/queries/tasks";
import type { Task, TaskStatus } from "@/lib/types/workflow";
import { useEffect, useState } from "react";

const STATUSES: TaskStatus[] = ["pending", "in_progress", "completed", "cancelled"];

export function TaskDetailSheet({
  task,
  onClose,
}: {
  task: Task | null;
  onClose: () => void;
}) {
  const [status, setStatus] = useState<TaskStatus>("pending");
  const [notes, setNotes] = useState("");
  const mutation = useTaskMutation();

  useEffect(() => {
    if (task) {
      setStatus(task.status);
      setNotes(task.description ?? "");
    }
  }, [task]);

  if (!task) return null;

  return (
    <Sheet open={!!task} onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{task.title}</SheetTitle>
          <SheetDescription>{task.task_type}</SheetDescription>
        </SheetHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="task-status">
              Status
            </label>
            <Select value={status} onValueChange={(v) => setStatus(v as TaskStatus)}>
              <SelectTrigger id="task-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="task-notes">
              Notes
            </label>
            <Textarea
              id="task-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={6}
            />
          </div>

          {mutation.isError && <p className="text-sm text-red-600">Failed to save changes.</p>}
        </div>

        <SheetFooter>
          <SheetClose asChild>
            <Button variant="outline">Cancel</Button>
          </SheetClose>
          <Button
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate(
                { id: task.id, patch: { status, description: notes } },
                { onSuccess: onClose },
              )
            }
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
