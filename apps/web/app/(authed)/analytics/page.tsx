import { LeakageTable } from "@/components/analytics/leakage-table";
import { PayerFrictionChart } from "@/components/analytics/payer-friction-chart";
import { ReferralQualityTable } from "@/components/analytics/referral-quality-table";
import { RoiSection } from "@/components/analytics/roi-section";
import { SummaryCards } from "@/components/analytics/summary-cards";
import { getDashboard, getRoi } from "@/lib/analytics";

interface PageProps {
  searchParams: Promise<{ from?: string; to?: string }>;
}

export default async function AnalyticsPage({
  searchParams,
}: PageProps): Promise<React.ReactElement> {
  const params = await searchParams;
  const dashboard = await getDashboard();
  const roi = params.from && params.to ? await getRoi(params.from, params.to) : dashboard.roi;

  return (
    <div className="px-8 py-6 space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-muted-foreground">
          Leakage risk, payer friction, referral source quality, and weekly ROI.
        </p>
      </header>

      <SummaryCards data={{ ...dashboard, roi }} />

      <RoiSection roi={roi} />

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Patients at risk</h2>
          <p className="text-sm text-muted-foreground">
            {dashboard.leakage.at_risk_count} above threshold ({dashboard.leakage.threshold})
          </p>
        </div>
        <LeakageTable rows={dashboard.leakage.rows} threshold={dashboard.leakage.threshold} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Payer friction</h2>
        <PayerFrictionChart rows={dashboard.payer_friction.rows} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Referral source quality</h2>
        <ReferralQualityTable rows={dashboard.referral_quality.rows} />
      </section>
    </div>
  );
}
