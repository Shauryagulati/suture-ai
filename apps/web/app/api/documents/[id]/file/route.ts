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
  const upstream = await fetch(`${API_URL}/api/documents/${id}/file`, {
    headers: { Authorization: `Bearer ${session.apiAccessToken}` },
  });

  if (!upstream.ok) {
    return NextResponse.json({ error: `upstream ${upstream.status}` }, { status: upstream.status });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/pdf",
      "content-disposition": upstream.headers.get("content-disposition") ?? "inline",
    },
  });
}
