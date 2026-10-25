import { NextResponse } from "next/server";

import { addVendor, getSession, writeSession } from "@/lib/session";

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url), 303);

  const form = await request.formData();
  const name = String(form.get("name") ?? "").trim().slice(0, 60);
  const email = String(form.get("email") ?? "").trim().slice(0, 80);
  if (!name || !/^[^@\s]+@[^@\s]+$/.test(email) || session.vendors.length >= 10) {
    return NextResponse.redirect(new URL("/vendors", request.url), 303);
  }
  addVendor(session, name, email);
  return writeSession(NextResponse.redirect(new URL("/vendors?added=1", request.url), 303), session);
}
