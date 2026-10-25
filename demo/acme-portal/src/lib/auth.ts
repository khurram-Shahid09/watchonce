import "server-only";

import { redirect } from "next/navigation";

import { getSession, type Session } from "./session";

/** For pages behind login: returns the session or redirects to /login. */
export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) redirect("/login");
  return session;
}
