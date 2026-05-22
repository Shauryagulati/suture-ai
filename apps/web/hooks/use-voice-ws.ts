"use client";

import { useEffect, useRef, useState } from "react";

import type { TranscriptStreamMessage } from "@/lib/voice-types";

type WsStatus = "connecting" | "open" | "closed" | "error";

interface UseVoiceWsResult {
  status: WsStatus;
  messages: TranscriptStreamMessage[];
  closeCode: number | null;
}

/**
 * Subscribes to /api/voice/calls/{callId}/stream and accumulates the
 * decoded messages. `apiBaseUrl` and `accessToken` come from the
 * server-rendered parent — NextAuth session isn't accessible from
 * client-side fetch in this app.
 *
 * The hook reconnects on transient disconnects for up to 5 attempts;
 * after that the consumer should refresh the page.
 */
export function useVoiceWs(params: {
  apiBaseUrl: string;
  callId: string;
  accessToken: string;
}): UseVoiceWsResult {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [messages, setMessages] = useState<TranscriptStreamMessage[]>([]);
  const [closeCode, setCloseCode] = useState<number | null>(null);
  const attemptsRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const wsUrl = new URL(`/api/voice/calls/${params.callId}/stream`, params.apiBaseUrl);
      wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";
      wsUrl.searchParams.set("token", params.accessToken);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => {
        if (!cancelled) {
          setStatus("open");
          attemptsRef.current = 0;
        }
      };

      ws.onmessage = (event) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(event.data) as TranscriptStreamMessage;
          setMessages((prev) => [...prev, msg]);
        } catch {
          // Ignore non-JSON frames.
        }
      };

      ws.onclose = (event) => {
        if (cancelled) return;
        setCloseCode(event.code);
        // 4xxx codes are app-level terminal closes — don't retry.
        if (event.code >= 4000 && event.code < 5000) {
          setStatus("closed");
          return;
        }
        // Transient close (e.g. server restart) — retry a few times.
        attemptsRef.current += 1;
        if (attemptsRef.current >= 5) {
          setStatus("error");
          return;
        }
        const delay = Math.min(1000 * 2 ** attemptsRef.current, 8000);
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        if (!cancelled) setStatus("error");
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [params.apiBaseUrl, params.callId, params.accessToken]);

  return { status, messages, closeCode };
}
