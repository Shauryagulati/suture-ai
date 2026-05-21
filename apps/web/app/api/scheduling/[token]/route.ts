// Public unauthed proxy: forwards to the backend's /api/schedule/{token}.
// No NextAuth — the signed token is the only credential needed.

import { type NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const upstream = await fetch(`${API_URL}/api/schedule/${token}`, {
    cache: "no-store",
  });
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
