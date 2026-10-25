import { NextResponse, type NextRequest } from "next/server";

import { formatVariant, parseVariant } from "@/lib/variant";

const VARIANT_COOKIE = "acme_variant"; // keep in sync with lib/ui-server.ts

/**
 * Per-browser UI variant override: append ?variant=v2 (or m1,m3 / original) to any URL.
 * ?variant=global removes the override so the portal-wide setting applies again.
 */
export function proxy(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("variant");
  if (raw === null) return NextResponse.next();

  const clean = request.nextUrl.clone();
  clean.searchParams.delete("variant");
  const res = NextResponse.redirect(clean, 303);

  if (raw.trim().toLowerCase() === "global") {
    res.cookies.delete(VARIANT_COOKIE);
    return res;
  }
  const mutations = parseVariant(raw);
  if (mutations === null) return new NextResponse(`Unknown variant "${raw}"`, { status: 400 });
  res.cookies.set(VARIANT_COOKIE, formatVariant(mutations), { path: "/", sameSite: "lax" });
  return res;
}

export const config = {
  matcher: ["/((?!_next/|api/|favicon.ico).*)"],
};
