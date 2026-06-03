"use client";

import { Pencil } from "lucide-react";
import { useState } from "react";

import { ConfidenceBadge } from "@/components/extraction/ConfidenceBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface FieldRowProps {
  path: string;
  value: unknown;
  confidence: number;
  isMissing: boolean;
  onSave: (newValue: unknown) => Promise<void>;
}

const HUMANIZE: Record<string, string> = {
  dob: "Date of birth",
  mrn: "MRN",
  npi: "NPI",
  cpt_code: "CPT code",
  zip_code: "ZIP",
  follow_up_window_days: "Follow-up window (days)",
};

function humanizeSegment(segment: string): string {
  const clean = segment.replace(/\[\d+\]$/, "");
  if (HUMANIZE[clean]) return HUMANIZE[clean];
  return clean.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizePath(path: string): string {
  return path.split(".").map(humanizeSegment).join(" › ");
}

function valueToInputString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map((v) => String(v)).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function inputStringToValue(raw: string, original: unknown): unknown {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  if (Array.isArray(original)) {
    return trimmed
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  if (typeof original === "number") {
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : trimmed;
  }
  return trimmed;
}

export function FieldRow({
  path,
  value,
  confidence,
  isMissing,
  onSave,
}: FieldRowProps): React.ReactElement {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(() => valueToInputString(value));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const display = isMissing
    ? "—"
    : value === null || value === undefined
      ? "—"
      : valueToInputString(value);

  async function handleSave(): Promise<void> {
    setIsSaving(true);
    setError(null);
    try {
      const newValue = inputStringToValue(draft, value);
      await onSave(newValue);
      setIsEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setIsSaving(false);
    }
  }

  function handleCancel(): void {
    setDraft(valueToInputString(value));
    setIsEditing(false);
    setError(null);
  }

  return (
    <div className="flex flex-col gap-1 border-b border-border py-2 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-muted-foreground">{humanizePath(path)}</div>
          {!isEditing ? (
            <div className="truncate text-sm" title={display}>
              {display}
            </div>
          ) : (
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  void handleSave();
                } else if (e.key === "Escape") {
                  handleCancel();
                }
              }}
              disabled={isSaving}
              className="mt-1"
            />
          )}
          {error ? <div className="mt-1 text-xs text-destructive">{error}</div> : null}
        </div>
        <div className="flex items-center gap-2">
          <ConfidenceBadge score={confidence} isMissing={isMissing} />
          {!isEditing ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setIsEditing(true)}
              aria-label={`Edit ${path}`}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
          ) : (
            <>
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={handleCancel} disabled={isSaving}>
                Cancel
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
