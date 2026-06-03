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
import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

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

type SortKey =
  | "status"
  | "classification"
  | "classification_confidence"
  | "urgency"
  | "file_name"
  | "created_at";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "classification", label: "Classification" },
  { key: "classification_confidence", label: "Confidence" },
  { key: "urgency", label: "Urgency" },
  { key: "file_name", label: "File" },
  { key: "created_at", label: "Uploaded" },
];

function compare(a: DocumentListItem, b: DocumentListItem, key: SortKey): number {
  if (key === "classification_confidence") {
    return (a.classification_confidence ?? -1) - (b.classification_confidence ?? -1);
  }
  if (key === "created_at") {
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  }
  return String(a[key] ?? "").localeCompare(String(b[key] ?? ""));
}

export function DocumentTable({ items }: Props): React.ReactElement {
  const router = useRouter();
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return items;
    const next = [...items].sort((a, b) => compare(a, b, sort.key));
    if (sort.dir === "desc") next.reverse();
    return next;
  }, [items, sort]);

  function toggleSort(key: SortKey): void {
    setSort((prev) =>
      prev?.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );
  }

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
            {COLUMNS.map((col) => {
              const active = sort?.key === col.key;
              const Icon = active ? (sort.dir === "asc" ? ChevronUp : ChevronDown) : ChevronsUpDown;
              return (
                <TableHead key={col.key}>
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key)}
                    className="-ml-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-foreground"
                  >
                    {col.label}
                    <Icon
                      className={`h-3.5 w-3.5 ${active ? "text-foreground" : "text-muted-foreground/50"}`}
                    />
                  </button>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((doc) => (
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
