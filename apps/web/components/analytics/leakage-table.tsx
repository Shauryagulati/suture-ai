"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { LeakageRow } from "@/lib/analytics-types";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { RiskScoreBadge } from "./risk-score-badge";

export function LeakageTable({
  rows,
  threshold,
}: {
  rows: LeakageRow[];
  threshold: number;
}): React.ReactElement {
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);

  const columns = useMemo<ColumnDef<LeakageRow>[]>(
    () => [
      { accessorKey: "patient_name", header: "Patient" },
      {
        accessorKey: "score",
        header: "Risk",
        cell: ({ row }) => <RiskScoreBadge score={row.original.score} threshold={threshold} />,
      },
      {
        accessorKey: "days_since_referral",
        header: "Days since",
        cell: ({ row }) => row.original.days_since_referral ?? "—",
      },
      { accessorKey: "failed_outreach_count", header: "Failed outreach" },
      {
        id: "contact",
        header: "Contact",
        cell: ({ row }) => {
          const r = row.original;
          if (r.has_phone && r.has_email) return <span className="text-emerald-700">Both</span>;
          if (r.has_phone || r.has_email)
            return (
              <span className="text-amber-700">{r.has_phone ? "Phone only" : "Email only"}</span>
            );
          return <span className="text-red-700">Missing</span>;
        },
      },
      { accessorKey: "urgency", header: "Urgency" },
      {
        id: "auth",
        header: "Auth",
        cell: ({ row }) =>
          row.original.prior_auth_denied ? <span className="text-red-700">Denied</span> : "—",
      },
    ],
    [threshold],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
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
          {rows.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="text-center text-muted-foreground py-6"
              >
                No patients above the risk threshold.
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
  );
}
