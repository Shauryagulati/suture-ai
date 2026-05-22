"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DischargeStatus } from "@/lib/discharges";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

type Props = {
  dischargeId: string;
  status: DischargeStatus;
  confirmationFaxSentAt: string | null;
};

export function ConfirmationPanel({
  dischargeId,
  status,
  confirmationFaxSentAt,
}: Props): React.ReactElement {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  async function onConfirm() {
    setError(null);
    const r = await fetch(`/api/discharges/${dischargeId}/confirm`, {
      method: "POST",
    });
    if (!r.ok) {
      let detail = `error ${r.status}`;
      try {
        const body = await r.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // body wasn't JSON — keep generic status
      }
      setError(detail);
      return;
    }
    startTransition(() => router.refresh());
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Confirmation fax</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {status === "confirmation_sent" ? (
          <>
            <p className="text-emerald-700 font-medium">
              ✓ Confirmation fax sent
              {confirmationFaxSentAt
                ? ` on ${new Date(confirmationFaxSentAt).toLocaleString()}`
                : ""}
            </p>
            <a
              href={`/api/discharges/${dischargeId}/fax`}
              className="inline-flex items-center text-sky-700 hover:underline"
            >
              Download PDF
            </a>
          </>
        ) : status === "seen" ? (
          <>
            <p className="text-muted-foreground">
              Patient visit complete. Generate and send the confirmation fax to the discharging
              hospital.
            </p>
            <Button onClick={onConfirm} disabled={isPending}>
              {isPending ? "Sending…" : "Generate Confirmation Fax"}
            </Button>
            {error && <p className="text-sm text-rose-600">{error}</p>}
          </>
        ) : (
          <p className="text-muted-foreground">
            Awaiting visit completion. Once the appointment is marked completed, the
            confirmation-fax action will appear here.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
