import { auth } from "@/auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(req: Request): Promise<Response> {
  const session = await auth();
  if (!session?.apiAccessToken) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const incoming = await req.formData();
  const file = incoming.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "file required" }, { status: 400 });
  }

  const outbound = new FormData();
  outbound.set("file", file, file.name);

  const upstream = await fetch(`${API_URL}/api/documents/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${session.apiAccessToken}` },
    body: outbound,
  });

  const text = await upstream.text();
  const contentType = upstream.headers.get("content-type") ?? "application/json";
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": contentType },
  });
}
