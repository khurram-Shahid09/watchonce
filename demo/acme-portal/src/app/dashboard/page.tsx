import type { Metadata } from "next";

import { requireSession } from "@/lib/auth";
import { formatMoney, formatUsDate, STATUS_LABEL } from "@/lib/data";
import { allInvoices, allVendors, DEMO_USER, vendorName } from "@/lib/session";
import { getUi } from "@/lib/ui-server";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const [session, ui] = await Promise.all([requireSession(), getUi()]);
  const invoices = allInvoices(session);
  const pending = invoices.filter((i) => i.status === "pending");
  const openCents = invoices.filter((i) => i.status !== "paid" && i.status !== "rejected").reduce((s, i) => s + i.amountCents, 0);

  const tiles: [string, string][] = [
    ["Open invoices", String(invoices.filter((i) => i.status === "pending" || i.status === "approved").length)],
    ["Pending approval", String(pending.length)],
    ["Open amount", formatMoney(openCents)],
    ["Active vendors", String(allVendors(session).length)],
  ];

  return (
    <>
      <h1>Welcome back, {DEMO_USER.name.split(" ")[0]}</h1>
      <div className={ui.cls("tiles")}>
        {tiles.map(([label, value]) => (
          <div key={label} className={ui.cls("tile")}>
            <div className={ui.cls("muted")}>{label}</div>
            <div className={ui.cls("tile-value")}>{value}</div>
          </div>
        ))}
      </div>
      <div className={ui.cls("card")}>
        <div className={ui.cls("card-title")}>Recent invoices</div>
        <table>
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Vendor</th>
              <th>Amount</th>
              <th>Due</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {invoices.slice(0, 5).map((inv) => (
              <tr key={inv.number}>
                <td>
                  <a href={`/invoices/${inv.number}`}>{inv.number}</a>
                </td>
                <td>{vendorName(session, inv.vendorId)}</td>
                <td>{formatMoney(inv.amountCents)}</td>
                <td>{formatUsDate(inv.due)}</td>
                <td>{STATUS_LABEL[inv.status]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          <a href="/invoices">View all invoices →</a>
        </p>
      </div>
    </>
  );
}
