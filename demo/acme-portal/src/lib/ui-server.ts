// Resolves the active UI variant for a request: this browser's override cookie wins,
// otherwise the portal-wide setting (the admin switch the live demo flips).
import "server-only";

import { cookies } from "next/headers";

import { makeUi, parseVariant, type Mutation, type Ui } from "./variant";

export const VARIANT_COOKIE = "acme_variant";

const store = globalThis as unknown as { __acmeGlobalVariant?: Mutation[] };

/**
 * Portal-wide variant, held in process memory (initial value from ACME_DEFAULT_VARIANT).
 * Reliable on a single long-running server (local, docker, VPS). On serverless hosts each
 * instance has its own copy, so use the per-browser ?variant= override there.
 */
export function getGlobalVariant(): Mutation[] {
  store.__acmeGlobalVariant ??= parseVariant(process.env.ACME_DEFAULT_VARIANT) ?? [];
  return store.__acmeGlobalVariant;
}

export function setGlobalVariant(mutations: Mutation[]): void {
  store.__acmeGlobalVariant = mutations;
}

export async function getVariant(): Promise<{ mutations: Mutation[]; source: "browser" | "global" }> {
  const override = parseVariant((await cookies()).get(VARIANT_COOKIE)?.value);
  if (override) return { mutations: override, source: "browser" };
  return { mutations: getGlobalVariant(), source: "global" };
}

export async function getUi(): Promise<Ui> {
  return makeUi((await getVariant()).mutations);
}
