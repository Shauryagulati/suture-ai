import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { notFound } from "next/navigation";
import { StatusActions } from "../_components/status-actions";
import type { PriorAuthDetail } from "../types";

async function loadDetail(id: string): Promise<PriorAuthDetail | null> {
  const resp = await apiFetch(`/api/prior-auth/${id}`);
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`prior-auth detail fetch failed: ${resp.status}`);
  return (await resp.json()) as PriorAuthDetail;
}

export default async function PriorAuthDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<React.ReactElement> {
  const { id } = await params;
  const pa = await loadDetail(id);
  if (pa === null) notFound();

  return (
    <div className="p-8 max-w-5xl space-y-6">
      <header>
        <p className="text-xs text-muted-foreground">Prior Authorization</p>
        <h1 className="text-2xl font-semibold tracking-tight">
          {pa.payer_name} — {pa.procedure_codes.join(", ")}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Status: <span className="font-medium">{pa.status.replace(/_/g, " ")}</span>
          {pa.auth_number ? ` · Auth # ${pa.auth_number}` : ""}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
          <Field label="Auth required" value={String(pa.auth_required ?? "unknown")} />
          <Field label="ICD-10" value={pa.diagnosis_codes.join(", ") || "—"} />
          <Field label="Submitted" value={pa.submitted_at ?? "—"} />
          <Field label="Approved" value={pa.approved_at ?? "—"} />
          <Field label="Denied" value={pa.denied_at ?? "—"} />
          <Field label="Follow-up at" value={pa.follow_up_at ?? "—"} />
          <div className="col-span-2 mt-3">
            <p className="text-xs font-medium text-muted-foreground mb-1">Reasoning</p>
            <p className="text-sm">{pa.auth_required_reasoning ?? "—"}</p>
          </div>
          {pa.packet_file_path && <Field label="Packet path" value={pa.packet_file_path} mono />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <StatusActions priorAuthId={pa.id} status={pa.status} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {pa.events.map((evt) => (
              <li key={evt.id} className="border-l-2 border-muted pl-3">
                <p className="text-sm font-medium">{evt.event_type.replace(/_/g, " ")}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(evt.created_at).toLocaleString()}
                </p>
                {Object.keys(evt.details).length > 0 && (
                  <pre className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap">
                    {JSON.stringify(evt.details, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}): React.ReactElement {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={mono ? "text-sm font-mono break-all" : "text-sm"}>{value}</p>
    </div>
  );
}
