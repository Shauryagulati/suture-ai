"use client";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { type TaskFilters, useTasksQuery } from "@/lib/queries/tasks";
import type { Task } from "@/lib/types/workflow";
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { FilterBar } from "./filter-bar";
import { SLABadge } from "./sla-badge";
import { StatusBadge } from "./status-badge";
import { TaskDetailSheet } from "./task-detail-sheet";

export function TaskTable() {
  const [filters, setFilters] = useState<TaskFilters>({});
  const [openTask, setOpenTask] = useState<Task | null>(null);
  const { data, isLoading, error } = useTasksQuery(filters);
  const rows = data?.items ?? [];

  const columns = useMemo<ColumnDef<Task>[]>(
    () => [
      { accessorKey: "title", header: "Title" },
      { accessorKey: "priority", header: "Priority" },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "due_at",
        header: "Due",
        cell: ({ row }) =>
          row.original.due_at ? new Date(row.original.due_at).toLocaleString() : "—",
      },
      {
        id: "sla",
        header: "SLA",
        cell: ({ row }) => <SLABadge dueAt={row.original.due_at} status={row.original.status} />,
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button size="sm" variant="ghost" onClick={() => setOpenTask(row.original)}>
            Open
          </Button>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div>
      <FilterBar filters={filters} onChange={setFilters} />
      {error && <p className="text-red-600 text-sm py-2">Failed to load tasks.</p>}
      {isLoading && <p className="text-muted-foreground py-2">Loading…</p>}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 && !isLoading ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="text-center text-muted-foreground py-6"
                >
                  No tasks match your filters.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((r) => (
                <TableRow key={r.id}>
                  {r.getVisibleCells().map((c) => (
                    <TableCell key={c.id}>
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      <TaskDetailSheet task={openTask} onClose={() => setOpenTask(null)} />
    </div>
  );
}
