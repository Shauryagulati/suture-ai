import { Sidebar } from "@/components/Sidebar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Activity } from "lucide-react";

const APP_VERSION = "0.1.0";

export default function HomePage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10">
        <div className="mx-auto max-w-3xl space-y-6">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-emerald-500/10 p-2">
                <Activity className="h-5 w-5 text-emerald-600" />
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">
                Suture — Operational · v{APP_VERSION}
              </h1>
            </div>
            <p className="text-muted-foreground">
              AI command center for cardiology practices. Foundation gates 0 → C must land before
              module work begins.
            </p>
          </header>

          <Card>
            <CardHeader>
              <CardTitle>Foundation status</CardTitle>
              <CardDescription>
                Gate A scaffold is alive. Auth, models, observability arrive in subsequent gates.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Gate 0 — Claude Code context" status="done" />
              <Row label="Gate A — Scaffold + infra + CI" status="active" />
              <Row label="Gate B1 — Tenant guard + audit + encryption" status="pending" />
              <Row label="Gate B2 — Auth flow" status="pending" />
              <Row label="Gate C — Full schema + seeds + obs" status="pending" />
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}

function Row({
  label,
  status,
}: {
  label: string;
  status: "done" | "active" | "pending";
}): React.ReactElement {
  const indicator =
    status === "done"
      ? "bg-emerald-500"
      : status === "active"
        ? "bg-amber-500"
        : "bg-muted-foreground/40";
  return (
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <span className={`inline-block h-2 w-2 rounded-full ${indicator}`} />
    </div>
  );
}
