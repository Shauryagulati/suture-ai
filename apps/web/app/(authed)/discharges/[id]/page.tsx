import { Sidebar } from "@/components/Sidebar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type DischargeStatus,
  type UrgencyTier,
  getDischarge,
  getDischargeTimeline,
} from "@/lib/discharges";
import { notFound } from "next/navigation";
import { ConfirmationPanel } from "./confirmation-panel";

const STATUS_TONE: Record<DischargeStatus, string> = {
  new: "bg-slate-100 text-slate-700",
  patient_contacted: "bg-sky-100 text-sky-700",
  scheduled: "bg-violet-100 text-violet-700",
  seen: "bg-amber-100 text-amber-700",
  confirmation_sent: "bg-emerald-100 text-emerald-700",
  at_risk: "bg-rose-100 text-rose-700",
};

const URGENCY_TONE: Record<UrgencyTier, string> = {
  critical: "bg-rose-100 text-rose-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-amber-100 text-amber-700",
  routine: "bg-slate-100 text-slate-700",
};

export default async function DischargeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<React.ReactElement> {
  const { id } = await params;

  let discharge: Awaited<ReturnType<typeof getDischarge>>;
  try {
    discharge = await getDischarge(id);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("404")) notFound();
    throw err;
  }
  const timeline = await getDischargeTimeline(id);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 max-w-5xl space-y-6">
        <header className="space-y-3">
          <p className="text-xs text-muted-foreground">Discharge follow-up</p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {discharge.patient_first_name} {discharge.patient_last_name}
          </h1>
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={STATUS_TONE[discharge.status]}>
              {discharge.status.replace(/_/g, " ")}
            </Badge>
            <Badge className={URGENCY_TONE[discharge.urgency_tier]}>
              {discharge.urgency_tier} urgency
            </Badge>
            <span className="text-sm text-muted-foreground">
              Discharged {discharge.discharge_date}
            </span>
          </div>
        </header>

        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Clinical details</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-y-2 text-sm">
              <Field label="Primary diagnosis" value={discharge.primary_diagnosis ?? "—"} />
              <Field label="ICD-10 codes" value={discharge.diagnosis_codes.join(", ") || "—"} />
              <Field label="Urgent flags" value={discharge.urgent_flags.join(", ") || "—"} />
              <Field
                label="Recommended specialist"
                value={discharge.recommended_specialist ?? "—"}
              />
              <Field
                label="Follow-up window"
                value={
                  discharge.follow_up_window_days ? `${discharge.follow_up_window_days} days` : "—"
                }
              />
              <Field label="Follow-up deadline" value={discharge.follow_up_deadline ?? "—"} />
            </CardContent>
          </Card>

          <ConfirmationPanel
            dischargeId={discharge.id}
            status={discharge.status}
            confirmationFaxSentAt={discharge.confirmation_fax_sent_at}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {timeline.events.length === 0 ? (
              <p className="text-sm text-muted-foreground">No events yet.</p>
            ) : (
              <ol className="space-y-3">
                {timeline.events.map((evt, idx) => (
                  <li
                    key={`${evt.resource_id}-${evt.at}-${idx}`}
                    className="border-l-2 border-muted pl-3"
                  >
                    <p className="text-sm font-medium">
                      {evt.action.replace(/_/g, " ")} ·{" "}
                      <span className="text-muted-foreground font-normal">{evt.resource_type}</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(evt.at).toLocaleString()}
                    </p>
                    {evt.changed_columns.length > 0 && (
                      <p className="text-xs text-muted-foreground mt-1">
                        changed: {evt.changed_columns.join(", ")}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string;
}): React.ReactElement {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  );
}
