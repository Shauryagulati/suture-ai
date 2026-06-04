"use client";

import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface TestCallResponse {
  call_id: string;
  test_caller_url: string;
  patient_name: string;
}

export function StartTestCallButton(): React.ReactElement {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick(): Promise<void> {
    setLoading(true);
    setError(null);
    // Open the tab synchronously inside the click handler so popup blockers
    // allow it; redirect it once we have the URL (can't use noopener here, or
    // we'd lose the handle needed to set its location).
    const tab = window.open("about:blank", "_blank");
    try {
      const resp = await fetch("/api/voice/test-call", { method: "POST" });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(detail.slice(0, 200) || `failed (${resp.status})`);
      }
      const body = (await resp.json()) as TestCallResponse;
      if (tab) {
        tab.location.href = body.test_caller_url;
      } else {
        // Popup blocked — navigate the current tab as a fallback.
        window.location.href = body.test_caller_url;
      }
      router.refresh(); // surface the new call in the active list
    } catch (e) {
      if (tab) tab.close();
      setError(e instanceof Error ? e.message : "could not start test call");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={handleClick} disabled={loading}>
        {loading ? "Starting…" : "Start test call"}
      </Button>
      {error ? <span className="text-xs text-destructive">{error}</span> : null}
    </div>
  );
}
