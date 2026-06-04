"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Polls the server component (via router.refresh) while documents are still
 * being processed in the background (OCR → classify → extract), so inbox rows
 * advance from "Uploaded" → "Extracted" without a manual reload. Renders
 * nothing and stops polling once nothing is in flight.
 */
export function InboxAutoRefresh({ active }: { active: boolean }): null {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => router.refresh(), 3000);
    return () => clearInterval(id);
  }, [active, router]);
  return null;
}
