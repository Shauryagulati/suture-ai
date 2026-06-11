"use client";

import { useEffect, useRef } from "react";

import { useVoiceWs } from "@/hooks/use-voice-ws";

interface TranscriptStreamProps {
  apiBaseUrl: string;
  callId: string;
  streamToken: string;
}

export function TranscriptStream({
  apiBaseUrl,
  callId,
  streamToken,
}: TranscriptStreamProps): React.ReactElement {
  const { status, messages, closeCode } = useVoiceWs({ apiBaseUrl, callId, streamToken });
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll on new messages. The hook depends on messages so React
  // re-runs it whenever a new chunk arrives; biome's "more deps than
  // necessary" complaint is wrong here — we want to fire on every change.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  return (
    <div className="flex h-full flex-col rounded-md border bg-card">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="text-sm font-medium">Live transcript</div>
        <StatusPill status={status} closeCode={closeCode} />
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
        {messages.length === 0 && status === "open" && (
          <p className="text-sm text-muted-foreground italic">Waiting for the first turn…</p>
        )}
        {messages.map((msg, idx) => {
          if (msg.type === "turn") {
            const isAgent = msg.role === "agent";
            return (
              <div
                key={`${idx}-${msg.ts}`}
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  isAgent
                    ? "bg-primary/10 text-foreground self-start"
                    : "bg-muted text-foreground self-end ml-auto"
                }`}
              >
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  {isAgent ? "Ember" : "Patient"}
                </div>
                {msg.text}
              </div>
            );
          }
          if (msg.type === "state") {
            return (
              <div
                key={`state-${idx}-${msg.state}`}
                className="text-xs text-muted-foreground italic text-center"
              >
                → {msg.state}
              </div>
            );
          }
          // end — only one of these will ever exist per call, so a fixed key is fine.
          return (
            <div
              key="end-marker"
              className="text-xs text-muted-foreground text-center pt-2 border-t mt-2"
            >
              Call ended.{" "}
              {typeof msg.outcome === "object" && msg.outcome !== null
                ? `booked_slot: ${String(
                    (msg.outcome as Record<string, unknown>).booked_slot ?? "—",
                  )}`
                : null}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function StatusPill({
  status,
  closeCode,
}: {
  status: "connecting" | "open" | "closed" | "error";
  closeCode: number | null;
}): React.ReactElement {
  const label =
    status === "open"
      ? "live"
      : status === "connecting"
        ? "connecting…"
        : status === "closed"
          ? `closed${closeCode ? ` (${closeCode})` : ""}`
          : "error";
  const color =
    status === "open" ? "bg-emerald-500" : status === "connecting" ? "bg-amber-500" : "bg-rose-500";
  return (
    <span className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}
