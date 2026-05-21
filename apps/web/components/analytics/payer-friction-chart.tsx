"use client";

import type { PayerFrictionRow } from "@/lib/analytics-types";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function PayerFrictionChart({ rows }: { rows: PayerFrictionRow[] }): React.ReactElement {
  if (rows.length === 0) {
    return <p className="text-muted-foreground text-sm">No prior auths yet.</p>;
  }
  const data = rows.map((r) => ({
    payer: r.payer_name,
    "Turnaround (days)": r.avg_turnaround_days ?? 0,
    "Approval %": Math.round(r.approval_rate * 100),
  }));
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="payer" angle={-20} textAnchor="end" height={60} fontSize={12} />
          <YAxis fontSize={12} />
          <Tooltip />
          <Legend />
          <Bar dataKey="Turnaround (days)" fill="#0ea5e9" />
          <Bar dataKey="Approval %" fill="#10b981" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
