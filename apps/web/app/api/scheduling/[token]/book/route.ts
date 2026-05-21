// Public unauthed proxy: forwards POST to /api/schedule/{token}/book.

import { type NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  const body = await req.text();
  const upstream = await fetch(`${API_URL}/api/schedule/${token}/book`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
