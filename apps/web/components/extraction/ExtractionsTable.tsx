"use client";

import { useRouter } from "next/navigation";

import { ClassificationBadge } from "@/components/inbox/badges";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ExtractionListItem } from "@/lib/extraction-types";

interface ExtractionsTableProps {
  items: ExtractionListItem[];
}

function confidenceBadge(score: number): React.ReactElement {
  const variant = score >= 0.8 ? "success" : score >= 0.5 ? "warning" : "destructive";
  return <Badge variant={variant}>{Math.round(score * 100)}%</Badge>;
}

export function ExtractionsTable({ items }: ExtractionsTableProps): React.ReactElement {
  const router = useRouter();
  if (items.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
        No extractions need review.
      </div>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Document</TableHead>
          <TableHead>Classification</TableHead>
          <TableHead className="w-32">Avg confidence</TableHead>
          <TableHead className="w-32">Missing</TableHead>
          <TableHead className="w-40">Created</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow
            key={item.id}
            className="cursor-pointer hover:bg-accent/40"
            onClick={() => router.push(`/inbox/${item.document_id}/review`)}
          >
            <TableCell className="font-medium">{item.document_file_name}</TableCell>
            <TableCell>
              <ClassificationBadge classification={item.classification} />
            </TableCell>
            <TableCell>{confidenceBadge(item.avg_confidence)}</TableCell>
            <TableCell>
              {item.missing_fields_count > 0 ? (
                <Badge variant="destructive">{item.missing_fields_count}</Badge>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {new Date(item.created_at).toLocaleString()}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
