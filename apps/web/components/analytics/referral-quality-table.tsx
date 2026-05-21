"use client";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ReferralQualityRow } from "@/lib/analytics-types";

export function ReferralQualityTable({
  rows,
}: {
  rows: ReferralQualityRow[];
}): React.ReactElement {
  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">No referrals attributed to a provider yet.</p>
    );
  }
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead>Practice</TableHead>
            <TableHead className="text-right">Volume</TableHead>
            <TableHead className="text-right">Completeness</TableHead>
            <TableHead>Top missing fields</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const pct = Math.round(r.completeness_pct * 100);
            const tone =
              pct >= 90
                ? "bg-emerald-100 text-emerald-900"
                : pct >= 70
                  ? "bg-amber-100 text-amber-900"
                  : "bg-red-100 text-red-900";
            return (
              <TableRow key={r.provider_id}>
                <TableCell>{r.provider_name}</TableCell>
                <TableCell className="text-muted-foreground">{r.practice_name ?? "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{r.referral_volume}</TableCell>
                <TableCell className="text-right">
                  <Badge className={tone}>{pct}%</Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {r.top_missing_fields.length ? r.top_missing_fields.join(", ") : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
