import { NextResponse } from "next/server";

import { formatUsDate, STATUS_LABEL } from "@/lib/data";
import { allInvoices, getSession, vendorName } from "@/lib/session";

export async function GET(request: Request) {
  const session = await getSession();
  if (!session) return NextResponse.redirect(new URL("/login", request.url), 303);

  const cell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const lines = [
    "invoice_number,vendor,description,amount,due_date,status",
    ...allInvoices(session).map((i) =>
      [i.number, vendorName(session, i.vendorId), i.description, (i.amountCents / 100).toFixed(2), formatUsDate(i.due), STATUS_LABEL[i.status]]
        .map(cell)
        .join(","),
    ),
  ];
  return new NextResponse(lines.join("\n") + "\n", {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="invoices.csv"',
    },
  });
}
