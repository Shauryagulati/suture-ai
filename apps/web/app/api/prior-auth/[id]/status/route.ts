import { apiFetch } from "@/lib/api";
import { NextResponse } from "next/server";

export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  const body = await req.text();
  const upstream = await apiFetch(`/api/prior-auth/${id}`, {
    method: "PATCH",
    body,
    headers: { "Content-Type": "application/json" },
  });
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
