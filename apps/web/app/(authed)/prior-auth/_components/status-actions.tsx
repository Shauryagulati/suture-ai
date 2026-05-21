"use client";

import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { useState } from "react";

type StatusName = "submitted" | "approved" | "denied";

export function StatusActions({
  priorAuthId,
  status,
}: {
  priorAuthId: string;
  status: string;
}): React.ReactElement {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [denialReason, setDenialReason] = useState("");
  const [authNumber, setAuthNumber] = useState("");

  async function patchStatus(next: StatusName, extra?: Record<string, string>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/prior-auth/${priorAuthId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next, ...extra }),
      });
      if (!resp.ok) {
        setError(`Server returned ${resp.status}: ${await resp.text()}`);
        return;
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function downloadAppeal(): Promise<void> {
    if (!denialReason.trim()) {
      setError("Enter the denial reason before generating an appeal.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`/api/prior-auth/${priorAuthId}/appeal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ denial_reason: denialReason }),
      });
      if (!resp.ok) {
        setError(`Server returned ${resp.status}`);
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = status === "required" || status === "checking";
  const canResolve = status === "submitted";
  const canAppeal = status === "denied" || status === "appeal_denied";

  return (
    <div className="space-y-3">
      {error && <p className="text-sm text-destructive">{error}</p>}

      {canSubmit && (
        <div className="flex items-center gap-2">
          <input
            value={authNumber}
            onChange={(e) => setAuthNumber(e.target.value)}
            placeholder="Auth # (optional)"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm w-48"
          />
          <Button
            disabled={busy}
            onClick={() =>
              patchStatus("submitted", authNumber ? { auth_number: authNumber } : undefined)
            }
          >
            Mark submitted
          </Button>
        </div>
      )}

      {canResolve && (
        <div className="flex items-center gap-2">
          <Button disabled={busy} onClick={() => patchStatus("approved")}>
            Mark approved
          </Button>
          <Button
            disabled={busy}
            variant="destructive"
            onClick={() =>
              patchStatus("denied", { denial_reason: denialReason || "(not provided)" })
            }
          >
            Mark denied
          </Button>
          <input
            value={denialReason}
            onChange={(e) => setDenialReason(e.target.value)}
            placeholder="Denial reason (if denying)"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm flex-1"
          />
        </div>
      )}

      {canAppeal && (
        <div className="flex items-center gap-2">
          <input
            value={denialReason}
            onChange={(e) => setDenialReason(e.target.value)}
            placeholder="Quote the denial reason verbatim"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm flex-1"
          />
          <Button disabled={busy || !denialReason.trim()} onClick={downloadAppeal}>
            Generate appeal letter
          </Button>
        </div>
      )}
    </div>
  );
}
