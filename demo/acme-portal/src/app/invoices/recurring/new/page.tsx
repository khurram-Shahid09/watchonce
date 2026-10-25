import type { Metadata } from "next";

import { requireSession } from "@/lib/auth";
import { getUi } from "@/lib/ui-server";

export const metadata: Metadata = { title: "New recurring invoice" };

/** Target of M5's decoy "New invoice" button. Reaching it means the wrong element was healed to. */
export default async function RecurringInvoicePage() {
  const [, ui] = await Promise.all([requireSession(), getUi()]);
  return (
    <div className={ui.cls("card")}>
      <div className={ui.cls("card-title")}>New recurring invoice template</div>
      <p>Recurring templates are managed by the finance team. Contact ap@acme.example to set one up.</p>
      <p>
        <a href="/invoices">← Back to invoices</a>
      </p>
    </div>
  );
}
