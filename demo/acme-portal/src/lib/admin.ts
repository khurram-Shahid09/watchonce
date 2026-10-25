import "server-only";

import { timingSafeEqual } from "node:crypto";

/** When ACME_ADMIN_TOKEN is set (public deployments), changing the portal-wide variant requires it. */
export function adminTokenOk(given: string): boolean {
  const expected = process.env.ACME_ADMIN_TOKEN;
  if (!expected) return true;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}
