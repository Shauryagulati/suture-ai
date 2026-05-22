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
  const upstream = await fetch(`${API_URL}/api/discharges/${id}/fax`, {
    method: "GET",
    headers: { Authorization: `Bearer ${session.apiAccessToken}` },
  });
  // Stream the PDF (or whatever upstream sent) through unmodified.
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/pdf",
      "content-disposition":
        upstream.headers.get("content-disposition") ??
        `attachment; filename="discharge-${id}-confirmation.pdf"`,
    },
  });
}
