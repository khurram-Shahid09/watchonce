import type { Metadata } from "next";

import { VendorDropdown } from "@/components/VendorDropdown";
import { Field } from "@/components/Wrap";
import { requireSession } from "@/lib/auth";
import { allVendors } from "@/lib/session";
import { getUi } from "@/lib/ui-server";

export const metadata: Metadata = { title: "New invoice" };

const ERRORS: Record<string, string> = {
  vendor: "Please choose a vendor.",
  amount: "Amount must be a positive number, e.g. 1250.50.",
  due: "Due date must be a valid date in MM/DD/YYYY format.",
};

export default async function NewInvoicePage({ searchParams }: PageProps<"/invoices/new">) {
  const [session, ui, params] = await Promise.all([requireSession(), getUi(), searchParams]);
  const prev = (key: string) => (typeof params[key] === "string" ? (params[key] as string) : "");
  const errors = prev("errors").split(",").filter((e) => e in ERRORS);
  const vendors = allVendors(session);

  return (
    <div className={ui.cls("card")}>
      <div className={ui.cls("card-title")}>New invoice</div>
      {errors.length ? (
        <div role="alert" className={ui.cls("alert alert-danger")}>
          {errors.map((e) => (
            <div key={e}>{ERRORS[e]}</div>
          ))}
        </div>
      ) : null}
      {vendors.length === 0 ? (
        <div role="alert" className={ui.cls("alert alert-warning")}>
          There are no vendors. Add a vendor before creating invoices.
        </div>
      ) : null}
      <form method="post" action="/invoices/new/submit" id="invoice-form" noValidate>
        <div className={ui.cls("form-grid")}>
          <Field ui={ui} id={ui.id("vendor")} label={ui.t("vendor")}>
            <VendorDropdown
              mutations={[...ui.mutations]}
              id={ui.id("vendor")}
              labelId={`${ui.id("vendor")}-label`}
              name="vendor_id"
              options={vendors.map((v) => ({ id: v.id, name: v.name }))}
              defaultValue={prev("vendor_id")}
            />
          </Field>
          <Field ui={ui} id={ui.id("amount")} label={ui.t("amount")} help="USD, e.g. 1250.50">
            <input
              id={ui.id("amount")}
              name="amount"
              inputMode="decimal"
              defaultValue={prev("amount")}
              className={ui.cls("form-control")}
              data-testid={ui.testid("invoice-amount")}
            />
          </Field>
          <Field ui={ui} id={ui.id("due-date")} label={ui.t("due_date")} help="MM/DD/YYYY">
            <input
              id={ui.id("due-date")}
              name="due"
              placeholder="MM/DD/YYYY"
              defaultValue={prev("due")}
              className={ui.cls("form-control")}
              data-testid={ui.testid("invoice-due-date")}
            />
          </Field>
          <Field ui={ui} id={ui.id("description")} label={ui.t("description")}>
            <input
              id={ui.id("description")}
              name="description"
              maxLength={60}
              defaultValue={prev("description")}
              className={ui.cls("form-control")}
            />
          </Field>
          <div className={ui.cls("form-actions")}>
            <button
              type="submit"
              id={ui.id("submit-invoice")}
              className={ui.cls("btn btn-primary")}
              data-testid={ui.testid("submit-invoice")}
            >
              {ui.t("submit")}
            </button>
            <a href="/invoices" className={ui.cls("btn")}>
              Cancel
            </a>
          </div>
        </div>
      </form>
    </div>
  );
}
