import { Card, CardContent } from "@/components/ui/card";
import type { RoiReport } from "@/lib/analytics-types";
import { DateRangePresets } from "./date-range-presets";

function fmtPct(n: number | null): string {
  return n == null ? "—" : `${(n * 100).toFixed(0)}%`;
}
function fmtDays(n: number | null): string {
  return n == null ? "—" : `${n.toFixed(1)} d`;
}
function fmtUSD(cents: number): string {
  return `$${(cents / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function RoiSection({ roi }: { roi: RoiReport }): React.ReactElement {
  const items = [
    { label: "Documents processed", value: roi.documents_processed.toLocaleString() },
    { label: "Hours saved", value: `${roi.hours_saved.toFixed(1)} h` },
    { label: "Referrals at risk", value: roi.referrals_at_risk.toLocaleString() },
    {
      label: "Projected revenue recovered",
      value: fmtUSD(roi.projected_revenue_recovered_cents),
    },
    { label: "Prior-auth approval rate", value: fmtPct(roi.prior_auth_approval_rate) },
    { label: "Avg days referral→appt", value: fmtDays(roi.avg_days_referral_to_appointment) },
  ];
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">ROI report</h2>
          <p className="text-sm text-muted-foreground">
            {roi.from_date} → {roi.to_date}
          </p>
        </div>
        <DateRangePresets from={roi.from_date} to={roi.to_date} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {items.map((it) => (
          <Card key={it.label}>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">{it.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{it.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
