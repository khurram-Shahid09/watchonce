// Seed data. Deterministic so recordings, evals and screenshots are reproducible.

export interface Vendor {
  id: string;
  name: string;
  email: string;
  city: string;
}

export type InvoiceStatus = "pending" | "approved" | "rejected" | "paid";

export interface Invoice {
  number: string;
  vendorId: string;
  amountCents: number;
  due: string; // ISO date
  description: string;
  status: InvoiceStatus;
  created?: boolean; // created in this session
}

const VENDOR_NAMES: [string, string][] = [
  ["Northwind Ltd", "Seattle"],
  ["Contoso Supplies", "Toronto"],
  ["Fabrikam Inc", "Chicago"],
  ["Adventure Works", "Denver"],
  ["Tailspin Toys", "Austin"],
  ["Wide World Importers", "Vancouver"],
  ["Litware Systems", "Boston"],
  ["Proseware Logistics", "Montreal"],
  ["Lucerne Publishing", "New York"],
  ["Woodgrove Freight", "Calgary"],
  ["Coho Vineyard", "Napa"],
  ["Alpine Ski House", "Banff"],
  ["Blue Yonder Airlines", "Dallas"],
  ["City Power & Light", "Ottawa"],
  ["Margie's Travel", "Miami"],
  ["Trey Research", "San Diego"],
  ["Graphic Design Institute", "Portland"],
  ["School of Fine Art", "Halifax"],
  ["Fourth Coffee", "Seattle"],
  ["Humongous Insurance", "Hartford"],
  ["Lamna Healthcare", "Winnipeg"],
  ["Relecloud", "Phoenix"],
  ["VanArsdel Ltd", "Edmonton"],
  ["Wingtip Toys", "Atlanta"],
];

export const SEED_VENDORS: Vendor[] = VENDOR_NAMES.map(([name, city], i) => ({
  id: `V-${String(i + 1).padStart(3, "0")}`,
  name,
  email: `ap@${name.toLowerCase().replace(/[^a-z]+/g, "")}.example`,
  city,
}));

// Small deterministic PRNG (mulberry32) for seed invoices.
function prng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const STATUSES: InvoiceStatus[] = ["paid", "approved", "pending", "paid", "rejected", "pending", "paid"];
const ITEMS = ["Office supplies", "Freight charges", "Consulting hours", "Hardware", "Software licences", "Catering", "Maintenance"];

export const SEED_INVOICES: Invoice[] = (() => {
  const rand = prng(42);
  return Array.from({ length: 34 }, (_, i) => {
    const day = 1 + Math.floor(rand() * 27);
    const month = 1 + ((i * 5) % 12);
    return {
      number: `INV-${100100 + i * 7}`,
      vendorId: SEED_VENDORS[Math.floor(rand() * SEED_VENDORS.length)].id,
      amountCents: Math.round((50 + rand() * 9500) * 100),
      due: `2026-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
      description: ITEMS[Math.floor(rand() * ITEMS.length)],
      status: STATUSES[i % STATUSES.length],
    };
  }).reverse();
})();

export function formatMoney(cents: number): string {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** ISO yyyy-mm-dd → MM/DD/YYYY, the portal's (US, legacy) display and input format. */
export function formatUsDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${m}/${d}/${y}`;
}

/** Parse "1250.5", "1,250.50", "$1,250.50" → cents. Null if invalid or not positive. */
export function parseAmount(raw: string): number | null {
  const cleaned = raw.trim().replace(/^\$/, "").replace(/,/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const cents = Math.round(parseFloat(cleaned) * 100);
  return cents > 0 && cents <= 100_000_000 ? cents : null;
}

/** Parse MM/DD/YYYY → ISO date. Null if malformed or not a real calendar date. */
export function parseUsDate(raw: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(raw.trim());
  if (!m) return null;
  const [, mm, dd, yyyy] = m;
  const date = new Date(Date.UTC(+yyyy, +mm - 1, +dd));
  if (date.getUTCFullYear() !== +yyyy || date.getUTCMonth() !== +mm - 1 || date.getUTCDate() !== +dd) return null;
  return `${yyyy}-${mm}-${dd}`;
}

export const STATUS_LABEL: Record<InvoiceStatus, string> = {
  pending: "Pending approval",
  approved: "Approved",
  rejected: "Rejected",
  paid: "Paid",
};
