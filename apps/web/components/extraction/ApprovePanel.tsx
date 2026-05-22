"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ExtractionApproveResponse, ExtractionDetail } from "@/lib/extraction-types";

interface ApprovePanelProps {
  extraction: ExtractionDetail;
}

export function ApprovePanel({ extraction }: ApprovePanelProps): React.ReactElement {
  const router = useRouter();
  const [isApproving, setIsApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const alreadyApproved = extraction.human_reviewed_at !== null;

  async function handleApprove(): Promise<void> {
    setIsApproving(true);
    setError(null);
    try {
      const resp = await fetch(`/api/extractions/${extraction.id}/approve`, {
        method: "POST",
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`approve failed (${resp.status}): ${detail.slice(0, 240)}`);
      }
      const body = (await resp.json()) as ExtractionApproveResponse;
      if (body.referral_id) {
        router.push(`/referrals/${body.referral_id}`);
      } else if (body.discharge_summary_id) {
        router.push(`/discharges/${body.discharge_summary_id}`);
      } else {
        router.refresh();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "approve failed");
    } finally {
      setIsApproving(false);
    }
  }

  return (
    <Card className="mt-4 flex flex-col gap-3 p-3">
      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <div>
          <div className="font-semibold uppercase tracking-wide">Model</div>
          <div className="font-mono text-foreground">{extraction.model ?? "—"}</div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide">Prompt</div>
          <div className="font-mono text-foreground">{extraction.prompt_version ?? "—"}</div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide">Avg confidence</div>
          <div className="font-mono text-foreground">
            {Math.round(extraction.avg_confidence * 100)}%
          </div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide">Extraction version</div>
          <div className="font-mono text-foreground">v{extraction.extraction_version}</div>
        </div>
      </div>

      {error ? <div className="text-xs text-destructive">{error}</div> : null}

      <Button onClick={handleApprove} disabled={isApproving || alreadyApproved} className="w-full">
        {alreadyApproved ? "Already approved" : isApproving ? "Approving…" : "Approve extraction"}
      </Button>
    </Card>
  );
}
