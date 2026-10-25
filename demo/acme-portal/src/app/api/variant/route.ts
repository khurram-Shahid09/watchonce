import { NextResponse } from "next/server";

import { adminTokenOk } from "@/lib/admin";
import { getGlobalVariant, setGlobalVariant } from "@/lib/ui-server";
import { formatVariant, parseVariant } from "@/lib/variant";

/** Portal-wide variant for eval harnesses. GET → {variant, mutations}; PUT {variant: "v2"} sets it. */
export async function GET() {
  const mutations = getGlobalVariant();
  return NextResponse.json({ variant: formatVariant(mutations), mutations });
}

export async function PUT(request: Request) {
  if (!adminTokenOk(request.headers.get("x-admin-token") ?? "")) {
    return NextResponse.json({ error: "invalid admin token" }, { status: 403 });
  }
  const body = (await request.json().catch(() => null)) as { variant?: unknown } | null;
  const mutations = typeof body?.variant === "string" ? parseVariant(body.variant) : null;
  if (mutations === null) {
    return NextResponse.json({ error: 'expected {"variant": "original" | "v2" | "m1,m3,..."}' }, { status: 400 });
  }
  setGlobalVariant(mutations);
  return NextResponse.json({ variant: formatVariant(mutations), mutations });
}
