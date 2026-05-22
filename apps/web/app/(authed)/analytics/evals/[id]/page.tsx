import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getEvalRun } from "@/lib/evals";

interface PageProps {
  params: Promise<{ id: string }>;
}

function pctBadge(score: number): React.ReactElement {
  const variant = score >= 0.85 ? "success" : score >= 0.65 ? "warning" : "destructive";
  return <Badge variant={variant}>{Math.round(score * 100)}%</Badge>;
}

export default async function EvalRunDetailPage({
  params,
}: PageProps): Promise<React.ReactElement> {
  const { id } = await params;
  const run = await getEvalRun(id).catch(() => null);
  if (!run) notFound();

  const fields = Object.entries(run.metrics.per_field).sort(
    (a, b) => a[1].accuracy - b[1].accuracy,
  );

  return (
    <div className="px-8 py-6">
      <div className="pb-3">
        <Link href="/analytics/evals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ChevronLeft className="mr-1 h-4 w-4" />
          Back to evals
        </Link>
      </div>

      <header className="pb-4">
        <h1 className="font-mono text-sm font-semibold tracking-tight">{run.id}</h1>
        <p className="text-sm text-muted-foreground">
          {run.test_set_version} · prompt {run.prompt_version ?? "—"} · {run.model ?? "—"} ·{" "}
          {new Date(run.created_at).toLocaleString()}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card className="p-3">
          <div className="text-xs text-muted-foreground">Samples</div>
          <div className="text-xl font-semibold">{run.num_samples}</div>
        </Card>
        <Card className="p-3">
          <div className="text-xs text-muted-foreground">Exact-match rate</div>
          <div className="text-xl font-semibold">
            {Math.round(run.metrics.aggregate.exact_match_rate * 100)}%
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-xs text-muted-foreground">F1 (macro)</div>
          <div className="text-xl font-semibold">
            {Math.round(run.metrics.aggregate.f1_macro * 100)}%
          </div>
        </Card>
        <Card className="p-3">
          <div className="text-xs text-muted-foreground">Duration</div>
          <div className="text-xl font-semibold">{run.run_duration_seconds}s</div>
        </Card>
      </div>

      <h2 className="mt-6 mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Per-field metrics (lowest accuracy first)
      </h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Field</TableHead>
            <TableHead className="w-24 text-right">n</TableHead>
            <TableHead className="w-32">Accuracy</TableHead>
            <TableHead className="w-32">Precision</TableHead>
            <TableHead className="w-32">Recall</TableHead>
            <TableHead className="w-32">F1</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map(([field, metrics]) => (
            <TableRow key={field}>
              <TableCell className="font-mono text-xs">{field}</TableCell>
              <TableCell className="text-right">{metrics.n}</TableCell>
              <TableCell>{pctBadge(metrics.accuracy)}</TableCell>
              <TableCell>{pctBadge(metrics.precision)}</TableCell>
              <TableCell>{pctBadge(metrics.recall)}</TableCell>
              <TableCell>{pctBadge(metrics.f1)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
