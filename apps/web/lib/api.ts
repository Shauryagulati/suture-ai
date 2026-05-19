import { auth } from "@/auth";

/**
 * Server-side fetch helper: pulls the API bearer from the NextAuth session
 * and prepends it. Use only from server components / route handlers.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const session = await auth();
  const apiUrl = process.env.API_URL ?? "http://localhost:8000";
  const headers = new Headers(init.headers);
  if (session?.apiAccessToken) {
    headers.set("Authorization", `Bearer ${session.apiAccessToken}`);
  }
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${apiUrl}${path}`, { ...init, headers });
}
