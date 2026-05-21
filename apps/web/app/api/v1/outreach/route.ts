import { apiFetch } from "@/lib/api";
import { type NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const search = req.nextUrl.search;
  const upstream = await apiFetch(`/api/outreach${search}`);
  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
