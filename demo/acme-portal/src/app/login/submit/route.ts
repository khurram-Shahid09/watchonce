import { NextResponse } from "next/server";

import { DEMO_USER, newSession, writeSession } from "@/lib/session";

export async function POST(request: Request) {
  const form = await request.formData();
  const username = String(form.get("username") ?? "").trim().toLowerCase();
  const password = String(form.get("password") ?? "");

  if (username !== DEMO_USER.username || password !== DEMO_USER.password) {
    return NextResponse.redirect(new URL("/login?error=1", request.url), 303);
  }
  return writeSession(NextResponse.redirect(new URL("/dashboard", request.url), 303), newSession(username));
}
