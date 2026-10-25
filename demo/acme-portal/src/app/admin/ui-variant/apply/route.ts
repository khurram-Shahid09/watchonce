import { NextResponse } from "next/server";

import { adminTokenOk } from "@/lib/admin";
import { setGlobalVariant, VARIANT_COOKIE } from "@/lib/ui-server";
import { formatVariant, parseVariant, type Mutation } from "@/lib/variant";

export async function POST(request: Request) {
  const form = await request.formData();
  const back = (query: string) => NextResponse.redirect(new URL(`/admin/ui-variant?${query}`, request.url), 303);

  const preset = form.get("preset");
  const mutations: Mutation[] | null =
    typeof preset === "string"
      ? parseVariant(preset)
      : form.getAll("mutation").length
        ? parseVariant(form.getAll("mutation").join(","))
        : [];
  if (mutations === null) return back("error=variant");

  const scope = form.get("scope") ?? "global";
  if (scope === "reset" || scope === "browser") {
    const res = back("saved=1");
    if (scope === "reset") res.cookies.delete(VARIANT_COOKIE);
    else res.cookies.set(VARIANT_COOKIE, formatVariant(mutations), { path: "/", sameSite: "lax" });
    return res;
  }

  if (!adminTokenOk(String(form.get("token") ?? ""))) return back("error=token");
  setGlobalVariant(mutations);
  return back("saved=1");
}
