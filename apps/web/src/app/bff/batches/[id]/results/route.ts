// Results CSV of a batch: input columns + status, error, run id and the outputs.

import { accessToken } from "@/lib/api";
import { API_URL } from "@/lib/session";

export async function GET(_request: Request, ctx: RouteContext<"/bff/batches/[id]/results">) {
  const { id } = await ctx.params;
  const token = await accessToken();
  if (!token) return new Response(null, { status: 401 });
  const upstream = await fetch(`${API_URL}/api/v1/batches/${encodeURIComponent(id)}/results.csv`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  }).catch(() => null);
  if (!upstream?.ok) return new Response(null, { status: upstream?.status ?? 502 });
  return new Response(upstream.body, {
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "text/csv",
      "Content-Disposition": upstream.headers.get("content-disposition") ?? `attachment; filename="results-${id}.csv"`,
    },
  });
}
