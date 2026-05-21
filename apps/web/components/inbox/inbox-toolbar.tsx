"use client";

import { UploadDropzone } from "@/components/inbox/upload-dropzone";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DocumentClassification, DocumentStatus, UrgencyLevel } from "@/lib/document-types";
import { Upload } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

const STATUS_OPTIONS: { value: DocumentStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "uploaded", label: "Uploaded" },
  { value: "classified", label: "Classified" },
  { value: "needs_review", label: "Needs review" },
  { value: "reviewed", label: "Reviewed" },
  { value: "error", label: "Error" },
];

const CLASSIFICATION_OPTIONS: { value: DocumentClassification | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "referral", label: "Referral" },
  { value: "discharge_summary", label: "Discharge summary" },
  { value: "lab", label: "Lab" },
  { value: "imaging", label: "Imaging" },
  { value: "other", label: "Other" },
  { value: "unclassified", label: "Unclassified" },
];

const URGENCY_OPTIONS: { value: UrgencyLevel | "all"; label: string }[] = [
  { value: "all", label: "All urgency" },
  { value: "stat", label: "STAT" },
  { value: "urgent", label: "Urgent" },
  { value: "routine", label: "Routine" },
  { value: "unclassified", label: "Unclassified" },
];

export function InboxToolbar(): React.ReactElement {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);

  function setFilter(key: string, value: string | undefined): void {
    const next = new URLSearchParams(searchParams.toString());
    if (!value || value === "all") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    router.push(`${pathname}?${next.toString()}`);
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pb-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={searchParams.get("status") ?? "all"}
          onValueChange={(v) => setFilter("status", v)}
        >
          <SelectTrigger className="w-[160px]">
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
        <Select
          value={searchParams.get("classification") ?? "all"}
          onValueChange={(v) => setFilter("classification", v)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CLASSIFICATION_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={searchParams.get("urgency") ?? "all"}
          onValueChange={(v) => setFilter("urgency", v)}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {URGENCY_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button onClick={() => setOpen(true)}>
        <Upload className="mr-2 h-4 w-4" />
        Upload PDF
      </Button>
      <UploadDropzone open={open} onOpenChange={setOpen} />
    </div>
  );
}
