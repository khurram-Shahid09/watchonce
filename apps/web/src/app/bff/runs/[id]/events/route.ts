// Live run events for the browser: the API's Server-Sent Events stream, passed through with
// the session token added here, so the browser never holds a token (docs/03, decision D11).

import { accessToken } from "@/lib/api";
import { API_URL } from "@/lib/session";

export async function GET(request: Request, ctx: RouteContext<"/bff/runs/[id]/events">) {
  const { id } = await ctx.params;
  const token = await accessToken();
  if (!token) return new Response(null, { status: 401 });
  const upstream = await fetch(`${API_URL}/api/v1/runs/${encodeURIComponent(id)}/events`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    cache: "no-store",
    signal: request.signal, // the viewer left: stop the upstream stream too
  }).catch(() => null);
  if (!upstream?.ok || !upstream.body) {
    return new Response(null, { status: upstream?.status === 404 ? 404 : 502 });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform", // no-transform: compression must not buffer it
      "X-Accel-Buffering": "no",
    },
  });
}
