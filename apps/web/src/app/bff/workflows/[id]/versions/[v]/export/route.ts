// Download a workflow version as a standalone Playwright (Python) script.

import { accessToken } from "@/lib/api";
import { API_URL } from "@/lib/session";

export async function GET(_request: Request, ctx: RouteContext<"/bff/workflows/[id]/versions/[v]/export">) {
  const { id, v } = await ctx.params;
  const token = await accessToken();
  if (!token) return new Response(null, { status: 401 });
  const upstream = await fetch(
    `${API_URL}/api/v1/workflows/${encodeURIComponent(id)}/versions/${encodeURIComponent(v)}/export/playwright`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  ).catch(() => null);
  if (!upstream?.ok) return new Response(null, { status: upstream?.status ?? 502 });
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/x-python; charset=utf-8",
      "Content-Disposition": upstream.headers.get("content-disposition") ?? `attachment; filename="workflow_v${v}.py"`,
    },
  });
}
