"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApprovePanel } from "@/components/extraction/ApprovePanel";
import { FieldRow } from "@/components/extraction/FieldRow";
import { MissingFieldsBanner } from "@/components/extraction/MissingFieldsBanner";
import { ClassificationBadge } from "@/components/inbox/badges";
import type { ExtractionDetail } from "@/lib/extraction-types";

interface ExtractionReviewPanelProps {
  initial: ExtractionDetail;
}

const INDEX_RE = /^(.*?)\[(\d+)\]$/;

function parsePathSegment(seg: string): { key: string; index: number | null } {
  const m = seg.match(INDEX_RE);
  if (m && m[1] !== undefined && m[2] !== undefined) {
    return { key: m[1], index: Number(m[2]) };
  }
  return { key: seg, index: null };
}

function getByPath(data: unknown, path: string): unknown {
  let current: unknown = data;
  for (const seg of path.split(".")) {
    const { key, index } = parsePathSegment(seg);
    if (current === null || current === undefined) return undefined;
    if (typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[key];
    if (index !== null) {
      if (!Array.isArray(current) || index >= current.length) return undefined;
      current = current[index];
    }
  }
  return current;
}

function groupFor(path: string): string {
  return path.split(".")[0] ?? path;
}

const GROUP_LABELS: Record<string, string> = {
  patient: "Patient",
  insurance: "Insurance",
  referring_provider: "Referring provider",
  attending_physician: "Attending physician",
  diagnosis_codes: "Codes",
  procedure_codes: "Codes",
  procedures_performed: "Procedures",
  medications_changed: "Medications",
  urgent_flags: "Urgency",
  urgency: "Urgency",
  urgency_tier: "Urgency",
  follow_up_window_days: "Follow-up",
  admit_date: "Encounter",
  discharge_date: "Encounter",
  discharging_hospital: "Encounter",
  primary_diagnosis: "Encounter",
  discharge_type: "Encounter",
  recommended_specialist: "Encounter",
  referral_type: "Encounter",
  clinical_notes_excerpt: "Notes",
};

export function ExtractionReviewPanel({ initial }: ExtractionReviewPanelProps): React.ReactElement {
  const router = useRouter();
  const [extraction, setExtraction] = useState(initial);

  const paths = Object.keys(extraction.field_confidences).sort((a, b) => {
    const ga = GROUP_LABELS[groupFor(a)] ?? "Other";
    const gb = GROUP_LABELS[groupFor(b)] ?? "Other";
    if (ga !== gb) return ga.localeCompare(gb);
    return a.localeCompare(b);
  });

  const groups = new Map<string, string[]>();
  for (const path of paths) {
    const label = GROUP_LABELS[groupFor(path)] ?? "Other";
    const arr = groups.get(label) ?? [];
    arr.push(path);
    groups.set(label, arr);
  }

  const missingSet = new Set(extraction.missing_fields);

  async function handleFieldSave(path: string, newValue: unknown): Promise<void> {
    const resp = await fetch(`/api/extractions/${extraction.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ field_path: path, new_value: newValue }),
    });
    if (!resp.ok) {
      const detail = await resp.text();
      throw new Error(`save failed (${resp.status}): ${detail.slice(0, 240)}`);
    }
    const updated = (await resp.json()) as ExtractionDetail;
    setExtraction(updated);
    router.refresh();
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-2">
          <ClassificationBadge classification={extraction.classification} />
          <span className="text-xs text-muted-foreground">
            v{extraction.extraction_version} · {extraction.document_file_name}
          </span>
        </div>
      </div>

      <div className="mt-3 flex-1 overflow-y-auto pr-1">
        <MissingFieldsBanner missingFields={extraction.missing_fields} />

        {[...groups.entries()].map(([label, groupPaths]) => (
          <div key={label} className="mt-4">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {label}
            </div>
            <div>
              {groupPaths.map((path) => (
                <FieldRow
                  key={path}
                  path={path}
                  value={getByPath(extraction.extraction_data, path)}
                  confidence={extraction.field_confidences[path] ?? 0}
                  isMissing={missingSet.has(path)}
                  onSave={(newValue) => handleFieldSave(path, newValue)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <ApprovePanel extraction={extraction} />
    </div>
  );
}
