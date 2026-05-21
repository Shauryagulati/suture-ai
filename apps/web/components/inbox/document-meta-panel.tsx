"use client";

import { ClassificationBadge, StatusBadge, UrgencyBadge } from "@/components/inbox/badges";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { DocumentDetail, DocumentStatus } from "@/lib/document-types";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

const STATUS_OPTIONS: { value: DocumentStatus; label: string }[] = [
  { value: "uploaded", label: "Uploaded" },
  { value: "classifying", label: "Classifying" },
  { value: "classified", label: "Classified" },
  { value: "needs_review", label: "Needs review" },
  { value: "reviewed", label: "Reviewed" },
  { value: "processed", label: "Processed" },
  { value: "error", label: "Error" },
];

interface Props {
  document: DocumentDetail;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function DocumentMetaPanel({ document }: Props): React.ReactElement {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<DocumentStatus>(document.status);
  const [notes, setNotes] = useState<string>(document.notes ?? "");
  const [pending, startTransition] = useTransition();

  async function save(): Promise<void> {
    const res = await fetch(`/api/documents/${document.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status, notes }),
    });
    if (!res.ok) {
      toast.error("Failed to save changes.");
      return;
    }
    toast.success("Saved.");
    await queryClient.invalidateQueries({ queryKey: ["documents"] });
    startTransition(() => router.refresh());
  }

  const confPct =
    document.classification_confidence != null
      ? `${Math.round(document.classification_confidence * 100)}%`
      : "—";

  return (
    <div className="flex h-full flex-col gap-4 rounded-md border bg-card p-4">
      <header>
        <h2 className="font-semibold text-lg leading-tight">{document.file_name}</h2>
        <p className="text-xs text-muted-foreground">
          {formatBytes(document.file_size)} · {document.mime_type} · uploaded{" "}
          {new Date(document.created_at).toLocaleString()}
        </p>
      </header>

      <Tabs defaultValue="summary" className="flex-1 overflow-hidden">
        <TabsList>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="text">Extracted text</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Classification">
              <ClassificationBadge classification={document.classification} />
            </Field>
            <Field label="Confidence">
              <span className="tabular-nums">{confPct}</span>
            </Field>
            <Field label="Status">
              <StatusBadge status={document.status} />
            </Field>
            <Field label="Urgency">
              <UrgencyBadge urgency={document.urgency} />
            </Field>
            <Field label="OCR engine">
              <span className="text-muted-foreground">{document.ocr_engine ?? "—"}</span>
            </Field>
            <Field label="Patient">
              <span className="text-muted-foreground">{document.patient_id ?? "Unlinked"}</span>
            </Field>
          </div>

          <div className="space-y-3 border-t pt-3">
            <h3 className="font-medium text-sm">Update</h3>
            <div className="space-y-1.5">
              <Label htmlFor="status-select">Status</Label>
              <Select value={status} onValueChange={(v) => setStatus(v as DocumentStatus)}>
                <SelectTrigger id="status-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="notes-input">Notes</Label>
              <Textarea
                id="notes-input"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Reviewer notes (not visible to patients)"
                rows={4}
              />
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => {
                  void save();
                }}
                disabled={pending}
              >
                {pending ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="text" className="h-full overflow-auto">
          {document.extracted_text ? (
            <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 text-xs leading-relaxed">
              {document.extracted_text}
            </pre>
          ) : (
            <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              No text extracted yet.
            </p>
          )}
        </TabsContent>

        <TabsContent value="activity">
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
            Activity timeline ships with workflow generation in Module 3a.
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="space-y-1">
      <div className="font-medium text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}
