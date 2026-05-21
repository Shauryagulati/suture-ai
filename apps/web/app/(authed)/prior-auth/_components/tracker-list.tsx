import type { PriorAuthRow } from "@/app/(authed)/prior-auth/types";
import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";

const STATUS_TONE: Record<string, string> = {
  not_needed: "bg-slate-100 text-slate-700",
  checking: "bg-slate-100 text-slate-700",
  required: "bg-amber-100 text-amber-800",
  submitted: "bg-blue-100 text-blue-800",
  approved: "bg-emerald-100 text-emerald-800",
  denied: "bg-rose-100 text-rose-800",
  appealing: "bg-violet-100 text-violet-800",
  appeal_approved: "bg-emerald-100 text-emerald-800",
  appeal_denied: "bg-rose-100 text-rose-800",
};

function StatusBadge({ status }: { status: string }): React.ReactElement {
  const tone = STATUS_TONE[status] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

export function TrackerList({ rows }: { rows: PriorAuthRow[] }): React.ReactElement {
  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No prior auths yet. Generate one from the inbox or referral pages.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Payer</th>
              <th className="px-4 py-2 text-left font-medium">CPT(s)</th>
              <th className="px-4 py-2 text-left font-medium">Status</th>
              <th className="px-4 py-2 text-left font-medium">Submitted</th>
              <th className="px-4 py-2 text-left font-medium">Follow-up</th>
              <th className="px-4 py-2 text-left font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t hover:bg-accent/40">
                <td className="px-4 py-2">
                  <Link href={`/prior-auth/${row.id}`} className="text-primary hover:underline">
                    {row.payer_name}
                  </Link>
                </td>
                <td className="px-4 py-2 font-mono text-xs">{row.procedure_codes.join(", ")}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={row.status} />
                </td>
                <td className="px-4 py-2 text-muted-foreground">{fmtDate(row.submitted_at)}</td>
                <td className="px-4 py-2 text-muted-foreground">{fmtDate(row.follow_up_at)}</td>
                <td className="px-4 py-2 text-muted-foreground">{fmtDate(row.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
