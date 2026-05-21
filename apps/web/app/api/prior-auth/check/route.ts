import { apiFetch } from "@/lib/api";
import { NextResponse } from "next/server";

export async function POST(req: Request): Promise<Response> {
  const body = await req.text();
  const upstream = await apiFetch("/api/prior-auth/check", {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
