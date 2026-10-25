// Run screenshots (after each step, and the one shown at a checkpoint).

import { accessToken } from "@/lib/api";
import { API_URL } from "@/lib/session";

export async function GET(_request: Request, ctx: RouteContext<"/bff/runs/[id]/screenshots/[name]">) {
  const { id, name } = await ctx.params;
  const token = await accessToken();
  if (!token) return new Response(null, { status: 401 });
  const upstream = await fetch(
    `${API_URL}/api/v1/runs/${encodeURIComponent(id)}/screenshots/${encodeURIComponent(name)}`,
    { headers: { Authorization: `Bearer ${token}` }, redirect: "manual", cache: "no-store" },
  ).catch(() => null);
  const location = upstream?.headers.get("location");
  if (!upstream || upstream.status !== 302 || !location) {
    return new Response(null, { status: upstream?.status === 404 ? 404 : 502 });
  }
  return new Response(null, {
    status: 302,
    headers: { Location: location, "Cache-Control": upstream.headers.get("cache-control") ?? "private, max-age=60" },
  });
}
