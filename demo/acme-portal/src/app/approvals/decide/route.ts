import { NextResponse } from "next/server";

import { allInvoices, getSession, writeSession } from "@/lib/session";

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url), 303);

  const form = await request.formData();
  const number = String(form.get("number") ?? "");
  const decision = form.get("decision");
  const invoice = allInvoices(session).find((i) => i.number === number && i.status === "pending");
  if (!invoice || (decision !== "approved" && decision !== "rejected")) {
    return NextResponse.redirect(new URL("/approvals", request.url), 303);
  }
  session.decisions[number] = decision;
  return writeSession(NextResponse.redirect(new URL(`/approvals?decided=${number}`, request.url), 303), session);
}
