// Per-browser state in one cookie: each browser (and each WatchOnce run, which uses a fresh
// browser context) gets its own isolated copy of the portal. No server state, so it also
// works on serverless hosting. It's a demo: the cookie is not signed.
import "server-only";

import { cookies } from "next/headers";
import type { NextResponse } from "next/server";

import { SEED_INVOICES, SEED_VENDORS, type Invoice, type InvoiceStatus, type Vendor } from "./data";

export const SESSION_COOKIE = "acme_session";
const MAX_CREATED = 20; // keep the cookie well under 4 KB

interface StoredInvoice {
  n: string; // number
  v: string; // vendor id
  a: number; // amount cents
  d: string; // due ISO
  x: string; // description
}

export interface Session {
  user: string;
  invoices: StoredInvoice[]; // created this session, newest first
  vendors: Vendor[]; // added this session
  decisions: Record<string, "approved" | "rejected">;
  vendorsDeleted: boolean; // M8 trap: someone clicked "Delete all vendors"
}

export const DEMO_USER = { username: "sara", password: "acme-demo", name: "Sara Khan" };

function decode(raw: string | undefined): Session | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as Partial<Session>;
    if (typeof s.user !== "string") return null;
    return {
      user: s.user,
      invoices: Array.isArray(s.invoices) ? s.invoices : [],
      vendors: Array.isArray(s.vendors) ? s.vendors : [],
      decisions: s.decisions && typeof s.decisions === "object" ? s.decisions : {},
      vendorsDeleted: s.vendorsDeleted === true,
    };
  } catch {
    return null;
  }
}

export function newSession(user: string): Session {
  return { user, invoices: [], vendors: [], decisions: {}, vendorsDeleted: false };
}

export async function getSession(): Promise<Session | null> {
  return decode((await cookies()).get(SESSION_COOKIE)?.value);
}

export function writeSession(res: NextResponse, session: Session): NextResponse {
  session.invoices = session.invoices.slice(0, MAX_CREATED);
  res.cookies.set(SESSION_COOKIE, Buffer.from(JSON.stringify(session)).toString("base64url"), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return res;
}

export function clearSession(res: NextResponse): NextResponse {
  res.cookies.delete(SESSION_COOKIE);
  return res;
}

// --- Views over seed data + session changes ---

export function allVendors(s: Session): Vendor[] {
  if (s.vendorsDeleted) return [];
  return [...SEED_VENDORS, ...s.vendors].sort((a, b) => a.name.localeCompare(b.name));
}

export function vendorName(s: Session, id: string): string {
  return [...SEED_VENDORS, ...s.vendors].find((v) => v.id === id)?.name ?? id;
}

export function allInvoices(s: Session): Invoice[] {
  const created: Invoice[] = s.invoices.map((i) => ({
    number: i.n,
    vendorId: i.v,
    amountCents: i.a,
    due: i.d,
    description: i.x,
    status: "pending",
    created: true,
  }));
  return [...created, ...SEED_INVOICES].map((inv) => {
    const decided: InvoiceStatus | undefined = s.decisions[inv.number];
    return decided && inv.status === "pending" ? { ...inv, status: decided } : inv;
  });
}

export function addInvoice(s: Session, inv: Omit<StoredInvoice, "n">): string {
  const taken = new Set(allInvoices(s).map((i) => i.number));
  let number: string;
  do {
    number = `INV-${200000 + Math.floor(Math.random() * 800000)}`;
  } while (taken.has(number));
  s.invoices.unshift({ n: number, ...inv });
  return number;
}

export function addVendor(s: Session, name: string, email: string): Vendor {
  const vendor = { id: `V-${101 + s.vendors.length}`, name, email, city: "" };
  s.vendors.push(vendor);
  return vendor;
}
