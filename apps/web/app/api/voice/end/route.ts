import { apiFetch } from "@/lib/api";
import { type NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const callId = req.nextUrl.searchParams.get("callId");
  if (!callId) {
    return NextResponse.json({ error: "missing callId" }, { status: 400 });
  }
  const upstream = await apiFetch(`/api/voice/calls/${callId}/end`, { method: "POST" });
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
