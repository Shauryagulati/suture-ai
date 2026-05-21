import { apiFetch } from "@/lib/api";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  const body = await req.text();
  const upstream = await apiFetch(`/api/prior-auth/${id}/appeal`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
  // PDF or JSON error — pass through bytes + content-type.
  const bytes = await upstream.arrayBuffer();
  return new Response(bytes, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Disposition":
        upstream.headers.get("Content-Disposition") ?? `inline; filename="appeal-${id}.pdf"`,
    },
  });
}
