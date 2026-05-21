"use client";

import { Button } from "@/components/ui/button";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

type Preset = "7d" | "30d" | "month" | "custom";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function isoStartOfMonth(): string {
  const d = new Date();
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)).toISOString().slice(0, 10);
}

export function DateRangePresets({
  from,
  to,
}: {
  from: string;
  to: string;
}): React.ReactElement {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [active, setActive] = useState<Preset>("30d");
  const [customFrom, setCustomFrom] = useState(from);
  const [customTo, setCustomTo] = useState(to);

  function apply(nextFrom: string, nextTo: string, preset: Preset): void {
    setActive(preset);
    const next = new URLSearchParams(sp.toString());
    next.set("from", nextFrom);
    next.set("to", nextTo);
    router.replace(`${pathname}?${next.toString()}`);
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="flex flex-wrap items-end gap-2">
      <Button
        size="sm"
        variant={active === "7d" ? "default" : "outline"}
        onClick={() => apply(isoDaysAgo(7), today, "7d")}
      >
        Last 7 days
      </Button>
      <Button
        size="sm"
        variant={active === "30d" ? "default" : "outline"}
        onClick={() => apply(isoDaysAgo(30), today, "30d")}
      >
        Last 30 days
      </Button>
      <Button
        size="sm"
        variant={active === "month" ? "default" : "outline"}
        onClick={() => apply(isoStartOfMonth(), today, "month")}
      >
        This month
      </Button>
      <div className="flex items-end gap-2 ml-2">
        <label className="text-xs text-muted-foreground flex flex-col">
          From
          <input
            type="date"
            value={customFrom}
            onChange={(e) => setCustomFrom(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-muted-foreground flex flex-col">
          To
          <input
            type="date"
            value={customTo}
            onChange={(e) => setCustomTo(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
          />
        </label>
        <Button size="sm" variant="secondary" onClick={() => apply(customFrom, customTo, "custom")}>
          Apply
        </Button>
      </div>
    </div>
  );
}
