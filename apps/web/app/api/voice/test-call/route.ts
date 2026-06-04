import { apiFetch } from "@/lib/api";
import { NextResponse } from "next/server";

export async function POST() {
  const upstream = await apiFetch("/api/voice/test-call", { method: "POST" });
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
