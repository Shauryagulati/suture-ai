import { ChannelIcon } from "@/components/outreach/channel-icon";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getOutreachDashboard } from "@/lib/outreach-dashboard";

const STATUS_TONE: Record<string, string> = {
  pending: "bg-slate-100 text-slate-700",
  sent: "bg-sky-100 text-sky-700",
  delivered: "bg-emerald-100 text-emerald-700",
  responded: "bg-emerald-100 text-emerald-700",
  no_response: "bg-amber-100 text-amber-700",
  failed: "bg-rose-100 text-rose-700",
};

function fmt(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default async function OutreachPage(): Promise<React.ReactElement> {
  const rows = await getOutreachDashboard();

  return (
    <div className="space-y-4 p-10">
      <div>
        <h1 className="text-2xl font-semibold">Outreach</h1>
        <p className="text-sm text-muted-foreground">
          {rows.length} outreach attempt{rows.length === 1 ? "" : "s"} — the exact message each
          patient receives across SMS, email, and voice.
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-md border border-dashed p-12 text-center text-sm text-muted-foreground">
          No outreach yet. Approve a referral or discharge to schedule the cadence.
        </div>
      ) : (
        <div className="rounded-md border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Channel</TableHead>
                <TableHead>Patient</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Scheduled</TableHead>
                <TableHead>Sent</TableHead>
                <TableHead>Message</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <span className="inline-flex items-center gap-2">
                      <ChannelIcon channel={r.channel} className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs uppercase text-muted-foreground">{r.channel}</span>
                    </span>
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className="font-medium">
                      {r.patient_first_name} {r.patient_last_name}
                    </span>
                    {r.related_type ? (
                      <Badge variant="outline" className="ml-2 capitalize">
                        {r.related_type}
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Badge className={STATUS_TONE[r.status] ?? ""}>
                      {r.status.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {fmt(r.scheduled_at)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {r.sent_at ? fmt(r.sent_at) : "—"}
                  </TableCell>
                  <TableCell className="max-w-md">
                    {r.message_subject ? (
                      <p className="text-xs font-medium">{r.message_subject}</p>
                    ) : null}
                    <p className="whitespace-pre-wrap text-xs text-muted-foreground line-clamp-3">
                      {r.message_body}
                    </p>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
