import { auth } from "@/auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await auth();
  if (!session?.apiAccessToken) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const upstream = await fetch(`${API_URL}/api/extractions/${id}`, {
    headers: { Authorization: `Bearer ${session.apiAccessToken}` },
    cache: "no-store",
  });

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const session = await auth();
  if (!session?.apiAccessToken) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const body = await req.text();
  const upstream = await fetch(`${API_URL}/api/extractions/${id}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${session.apiAccessToken}`,
      "content-type": "application/json",
    },
    body,
  });

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
