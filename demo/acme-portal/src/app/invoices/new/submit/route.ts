import { NextResponse } from "next/server";

import { parseAmount, parseUsDate } from "@/lib/data";
import { addInvoice, allVendors, getSession, writeSession } from "@/lib/session";

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url), 303);

  const form = await request.formData();
  const field = (k: string) => String(form.get(k) ?? "").trim();
  const vendorId = field("vendor_id");
  const amount = parseAmount(field("amount"));
  const due = parseUsDate(field("due"));

  const errors: string[] = [];
  if (!allVendors(session).some((v) => v.id === vendorId)) errors.push("vendor");
  if (amount === null) errors.push("amount");
  if (due === null) errors.push("due");

  if (errors.length || amount === null || due === null) {
    const back = new URL("/invoices/new", request.url);
    for (const k of ["vendor_id", "amount", "due", "description"]) back.searchParams.set(k, field(k));
    back.searchParams.set("errors", errors.join(","));
    return NextResponse.redirect(back, 303);
  }

  const number = addInvoice(session, { v: vendorId, a: amount, d: due, x: field("description").slice(0, 60) });
  const res = NextResponse.redirect(new URL(`/invoices/${number}?created=1`, request.url), 303);
  return writeSession(res, session);
}
