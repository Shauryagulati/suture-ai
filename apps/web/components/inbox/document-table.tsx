"use client";

import { ClassificationBadge, StatusBadge, UrgencyBadge } from "@/components/inbox/badges";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DocumentListItem } from "@/lib/document-types";
import { useRouter } from "next/navigation";

interface Props {
  items: DocumentListItem[];
}

const RELATIVE_TIME = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = (then - Date.now()) / 1000;
  const absSec = Math.abs(diffSec);
  if (absSec < 60) return RELATIVE_TIME.format(Math.round(diffSec), "second");
  if (absSec < 3600) return RELATIVE_TIME.format(Math.round(diffSec / 60), "minute");
  if (absSec < 86_400) return RELATIVE_TIME.format(Math.round(diffSec / 3600), "hour");
  return RELATIVE_TIME.format(Math.round(diffSec / 86_400), "day");
}

function confidence(value: number | null): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function DocumentTable({ items }: Props): React.ReactElement {
  const router = useRouter();

  if (items.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-12 text-center">
        <p className="text-sm text-muted-foreground">
          No documents yet. Upload a referral or discharge PDF to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Status</TableHead>
            <TableHead>Classification</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>Urgency</TableHead>
            <TableHead>File</TableHead>
            <TableHead>Uploaded</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((doc) => (
            <TableRow
              key={doc.id}
              className="cursor-pointer"
              onClick={() => router.push(`/inbox/${doc.id}`)}
            >
              <TableCell>
                <StatusBadge status={doc.status} />
              </TableCell>
              <TableCell>
                <ClassificationBadge classification={doc.classification} />
              </TableCell>
              <TableCell className="text-sm tabular-nums">
                {confidence(doc.classification_confidence)}
              </TableCell>
              <TableCell>
                <UrgencyBadge urgency={doc.urgency} />
              </TableCell>
              <TableCell className="max-w-xs truncate text-sm">{doc.file_name}</TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {relativeTime(doc.created_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
