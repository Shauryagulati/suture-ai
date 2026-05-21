import { apiFetch } from "@/lib/api";
import { type NextRequest, NextResponse } from "next/server";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const upstream = await apiFetch(`/api/outreach/${id}`);
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
