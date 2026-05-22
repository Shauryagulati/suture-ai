import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listEvalRuns } from "@/lib/evals";

function pctBadge(score: number): React.ReactElement {
  const variant = score >= 0.85 ? "success" : score >= 0.65 ? "warning" : "destructive";
  return <Badge variant={variant}>{Math.round(score * 100)}%</Badge>;
}

export default async function EvalListPage(): Promise<React.ReactElement> {
  const result = await listEvalRuns();

  return (
    <div className="px-8 py-6">
      <header className="pb-4">
        <h1 className="font-semibold text-2xl tracking-tight">Extraction evals</h1>
        <p className="text-sm text-muted-foreground">
          {result.total} run{result.total === 1 ? "" : "s"}
        </p>
      </header>

      {result.items.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
          No eval runs yet — run <code className="font-mono">make eval-extraction</code> to
          populate.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Run</TableHead>
              <TableHead>Prompt</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="w-24 text-right">Samples</TableHead>
              <TableHead className="w-32">Exact match</TableHead>
              <TableHead className="w-32">F1 (macro)</TableHead>
              <TableHead className="w-40">Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.items.map((run) => (
              <TableRow key={run.id}>
                <TableCell>
                  <Link
                    href={`/analytics/evals/${run.id}`}
                    className="font-mono text-xs text-primary hover:underline"
                  >
                    {run.id.slice(0, 8)}…
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs">{run.prompt_version ?? "—"}</TableCell>
                <TableCell className="font-mono text-xs">{run.model ?? "—"}</TableCell>
                <TableCell className="text-right">{run.num_samples}</TableCell>
                <TableCell>{pctBadge(run.exact_match_rate)}</TableCell>
                <TableCell>{pctBadge(run.f1_macro)}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {new Date(run.created_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
