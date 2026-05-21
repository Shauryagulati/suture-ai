import { apiFetch } from "@/lib/api";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ referralId: string }> },
): Promise<Response> {
  const { referralId } = await params;
  const body = await req.text();
  const upstream = await apiFetch(`/api/prior-auth/packet/${referralId}`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
