import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import type { CallResponse } from "@/lib/voice-types";

interface CallListProps {
  calls: CallResponse[];
}

function statusColor(status: CallResponse["status"]): string {
  switch (status) {
    case "initiated":
      return "bg-amber-100 text-amber-900";
    case "in_progress":
      return "bg-emerald-100 text-emerald-900";
    case "completed":
      return "bg-slate-100 text-slate-700";
    case "failed":
    case "no_answer":
    case "voicemail":
      return "bg-rose-100 text-rose-900";
  }
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function CallList({ calls }: CallListProps): React.ReactElement {
  if (calls.length === 0) {
    return (
      <div className="rounded-md border bg-card p-8 text-center text-sm text-muted-foreground">
        No active calls. Ember will appear here when a voice attempt is dispatched.
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">Call</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Started</th>
            <th className="px-4 py-3 font-medium">Duration</th>
            <th className="px-4 py-3 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y">
          {calls.map((c) => (
            <tr key={c.id} className="hover:bg-muted/30">
              <td className="px-4 py-3 font-mono text-xs">{c.id.slice(0, 8)}…</td>
              <td className="px-4 py-3">
                <Badge className={statusColor(c.status)}>{c.status}</Badge>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{c.call_type}</td>
              <td className="px-4 py-3 text-muted-foreground">
                {new Date(c.started_at).toLocaleString()}
              </td>
              <td className="px-4 py-3 text-muted-foreground">{fmtDuration(c.duration_seconds)}</td>
              <td className="px-4 py-3 text-right">
                <Link href={`/voice/${c.id}`} className="text-primary hover:underline">
                  Open →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
