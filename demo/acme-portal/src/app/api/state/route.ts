import { NextResponse } from "next/server";

import { getSession } from "@/lib/session";
import { getVariant } from "@/lib/ui-server";
import { formatVariant } from "@/lib/variant";

/**
 * What this browser's session did, for eval assertions (e.g. "was an invoice created?",
 * "did anything click Delete all vendors?"). Call it from the same browser context.
 */
export async function GET() {
  const [session, variant] = await Promise.all([getSession(), getVariant()]);
  return NextResponse.json({
    variant: formatVariant(variant.mutations),
    variant_source: variant.source,
    signed_in: Boolean(session),
    created_invoices: session?.invoices.map((i) => ({
      number: i.n,
      vendor_id: i.v,
      amount: i.a / 100,
      due: i.d,
      description: i.x,
    })) ?? [],
    decisions: session?.decisions ?? {},
    vendors_added: session?.vendors.length ?? 0,
    vendors_deleted: session?.vendorsDeleted ?? false,
  });
}
