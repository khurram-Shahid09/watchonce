import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { requireSession } from "@/lib/auth";
import { formatMoney, formatUsDate, STATUS_LABEL } from "@/lib/data";
import { allInvoices, vendorName } from "@/lib/session";
import { getUi } from "@/lib/ui-server";

export async function generateMetadata({ params }: PageProps<"/invoices/[number]">): Promise<Metadata> {
  return { title: (await params).number };
}

export default async function InvoicePage({ params, searchParams }: PageProps<"/invoices/[number]">) {
  const [session, ui, { number }, query] = await Promise.all([requireSession(), getUi(), params, searchParams]);
  const invoice = allInvoices(session).find((i) => i.number === number);
  if (!invoice) notFound();

  return (
    <>
      {query.created && invoice.created ? (
        <div role="status" className={ui.cls("alert alert-success")}>
          Invoice created. It has been sent for approval.
        </div>
      ) : null}
      <div className={ui.cls("card")}>
        <div className={ui.cls("card-title")}>
          Invoice{" "}
          <span className={ui.cls("invoice-number")} data-testid={ui.testid("invoice-number")}>
            {invoice.number}
          </span>
        </div>
        <table style={{ width: "auto" }}>
          <tbody>
            <tr>
              <th>Vendor</th>
              <td>{vendorName(session, invoice.vendorId)}</td>
            </tr>
            <tr>
              <th>Amount</th>
              <td>{formatMoney(invoice.amountCents)}</td>
            </tr>
            <tr>
              <th>Due date</th>
              <td>{formatUsDate(invoice.due)}</td>
            </tr>
            <tr>
              <th>Description</th>
              <td>{invoice.description || "—"}</td>
            </tr>
            <tr>
              <th>Status</th>
              <td>
                <span className={ui.cls(`badge badge-${invoice.status}`)}>{STATUS_LABEL[invoice.status]}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          <a href="/invoices">← Back to invoices</a>
        </p>
      </div>
    </>
  );
}
