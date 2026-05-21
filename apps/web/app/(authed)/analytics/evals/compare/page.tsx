import { ChevronLeft } from "lucide-react";
import Link from "next/link";

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
import { compareEvalRuns } from "@/lib/evals";
import { cn } from "@/lib/utils";

interface PageProps {
  searchParams: Promise<{ run_a?: string; run_b?: string }>;
}

function deltaClass(delta: number): string {
  if (delta > 0.05) return "text-emerald-700 dark:text-emerald-400 font-semibold";
  if (delta < -0.05) return "text-red-700 dark:text-red-400 font-semibold";
  return "text-muted-foreground";
}

function pct(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  return `${Math.round(n * 100)}%`;
}

export default async function EvalCompareePage({
  searchParams,
}: PageProps): Promise<React.ReactElement> {
  const sp = await searchParams;
  if (!sp.run_a || !sp.run_b) {
    return (
      <div className="px-8 py-6">
        <p className="text-sm text-muted-foreground">
          Provide both <code>?run_a=</code> and <code>?run_b=</code> in the URL.
        </p>
      </div>
    );
  }
  const cmp = await compareEvalRuns(sp.run_a, sp.run_b);

  return (
    <div className="px-8 py-6">
      <div className="pb-3">
        <Link href="/analytics/evals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ChevronLeft className="mr-1 h-4 w-4" />
          Back to evals
        </Link>
      </div>
      <header className="pb-4">
        <h1 className="font-semibold text-2xl tracking-tight">Compare runs</h1>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">{cmp.run_a_id.slice(0, 8)}…</span> →{" "}
          <span className="font-mono">{cmp.run_b_id.slice(0, 8)}…</span>
        </p>
      </header>

      <Card className="mb-4 p-3">
        <div className="text-xs text-muted-foreground">Aggregate exact-match delta</div>
        <div className={cn("text-2xl font-semibold", deltaClass(cmp.aggregate_delta))}>
          {cmp.aggregate_delta > 0 ? "+" : ""}
          {Math.round(cmp.aggregate_delta * 100)}%
        </div>
      </Card>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Field</TableHead>
            <TableHead className="w-32">Run A accuracy</TableHead>
            <TableHead className="w-32">Run B accuracy</TableHead>
            <TableHead className="w-24 text-right">Delta</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {cmp.fields.map((f) => (
            <TableRow key={f.field}>
              <TableCell className="font-mono text-xs">{f.field}</TableCell>
              <TableCell>{pct(f.run_a?.accuracy)}</TableCell>
              <TableCell>{pct(f.run_b?.accuracy)}</TableCell>
              <TableCell className={cn("text-right tabular-nums", deltaClass(f.delta))}>
                {f.delta > 0 ? "+" : ""}
                {(f.delta * 100).toFixed(1)}%
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
