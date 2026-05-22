import { Card, CardContent } from "@/components/ui/card";
import type { DashboardPayload } from "@/lib/analytics-types";

function fmtPct(n: number | null): string {
  return n == null ? "—" : `${(n * 100).toFixed(0)}%`;
}

function fmtDays(n: number | null): string {
  return n == null ? "—" : `${n.toFixed(1)} d`;
}

export function SummaryCards({ data }: { data: DashboardPayload }): React.ReactElement {
  const items = [
    { label: "Documents processed (30d)", value: data.roi.documents_processed.toLocaleString() },
    {
      label: "Patients at risk",
      value: data.leakage.at_risk_count.toLocaleString(),
      tone: "danger" as const,
    },
    { label: "Avg days to appointment", value: fmtDays(data.roi.avg_days_referral_to_appointment) },
    { label: "Prior-auth approval rate", value: fmtPct(data.roi.prior_auth_approval_rate) },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map((item) => (
        <Card key={item.label}>
          <CardContent className="p-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">{item.label}</p>
            <p
              className={`mt-2 text-3xl font-semibold tabular-nums ${
                item.tone === "danger" ? "text-red-700" : ""
              }`}
            >
              {item.value}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
