"use client";

import { Badge } from "@/components/ui/badge";
import type { DocumentClassification, DocumentStatus, UrgencyLevel } from "@/lib/document-types";

type StatusVariant = "default" | "secondary" | "destructive" | "outline" | "muted" | "warning";

const STATUS_VARIANT: Record<DocumentStatus, StatusVariant> = {
  uploaded: "secondary",
  classifying: "warning",
  classified: "outline",
  extracting: "warning",
  extracted: "outline",
  needs_review: "destructive",
  reviewed: "default",
  processed: "default",
  error: "destructive",
};

const CLASSIFICATION_VARIANT: Record<DocumentClassification, StatusVariant> = {
  referral: "default",
  discharge_summary: "secondary",
  lab: "outline",
  imaging: "outline",
  other: "muted",
  unclassified: "muted",
};

const URGENCY_VARIANT: Record<UrgencyLevel, StatusVariant> = {
  stat: "destructive",
  urgent: "warning",
  routine: "secondary",
  unclassified: "muted",
};

const HUMANIZE: Record<string, string> = {
  discharge_summary: "Discharge summary",
  needs_review: "Needs review",
};

function humanize(value: string): string {
  return HUMANIZE[value] ?? value.charAt(0).toUpperCase() + value.slice(1);
}

export function StatusBadge({ status }: { status: DocumentStatus }): React.ReactElement {
  return <Badge variant={STATUS_VARIANT[status]}>{humanize(status)}</Badge>;
}

export function ClassificationBadge({
  classification,
}: {
  classification: DocumentClassification;
}): React.ReactElement {
  return <Badge variant={CLASSIFICATION_VARIANT[classification]}>{humanize(classification)}</Badge>;
}

export function UrgencyBadge({ urgency }: { urgency: UrgencyLevel }): React.ReactElement {
  return <Badge variant={URGENCY_VARIANT[urgency]}>{humanize(urgency)}</Badge>;
}
