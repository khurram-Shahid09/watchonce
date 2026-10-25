import type { Metadata } from "next";

import { requireSession } from "@/lib/auth";
import { formatMoney, formatUsDate } from "@/lib/data";
import { allInvoices, vendorName } from "@/lib/session";
import { getUi } from "@/lib/ui-server";

export const metadata: Metadata = { title: "Approvals" };

export default async function ApprovalsPage({ searchParams }: PageProps<"/approvals">) {
  const [session, ui, params] = await Promise.all([requireSession(), getUi(), searchParams]);
  const pending = allInvoices(session).filter((i) => i.status === "pending");
  const decided = typeof params.decided === "string" ? params.decided : "";

  return (
    <>
      <h1>Pending approvals</h1>
      {decided ? (
        <div role="status" className={ui.cls("alert alert-success")}>
          {decided} updated.
        </div>
      ) : null}
      {pending.length === 0 ? (
        <p className={ui.cls("muted")}>Nothing waiting for approval.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Vendor</th>
              <th>Amount</th>
              <th>Due</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {pending.map((inv) => (
              <tr key={inv.number}>
                <td>
                  <a href={`/invoices/${inv.number}`}>{inv.number}</a>
                </td>
                <td>{vendorName(session, inv.vendorId)}</td>
                <td>{formatMoney(inv.amountCents)}</td>
                <td>{formatUsDate(inv.due)}</td>
                <td>
                  <form method="post" action="/approvals/decide" style={{ display: "flex", gap: 4 }}>
                    <input type="hidden" name="number" value={inv.number} />
                    <button type="submit" name="decision" value="approved" className={ui.cls("btn btn-primary btn-sm")}>
                      {ui.t("approve")}
                    </button>
                    <button type="submit" name="decision" value="rejected" className={ui.cls("btn btn-sm")}>
                      {ui.t("reject")}
                    </button>
                  </form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
