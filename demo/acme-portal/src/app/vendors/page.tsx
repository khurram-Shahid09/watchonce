import type { Metadata } from "next";

import { AddVendorModal } from "@/components/Disclosure";
import { requireSession } from "@/lib/auth";
import { allVendors } from "@/lib/session";
import { getUi } from "@/lib/ui-server";

export const metadata: Metadata = { title: "Vendors" };

export default async function VendorsPage({ searchParams }: PageProps<"/vendors">) {
  const [session, ui, params] = await Promise.all([requireSession(), getUi(), searchParams]);
  const q = typeof params.q === "string" ? params.q.trim() : "";
  const vendors = allVendors(session).filter((v) => !q || v.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <h1>Vendors</h1>
      {session.vendorsDeleted ? (
        <div role="alert" className={ui.cls("alert alert-danger")}>
          All vendors were deleted.
        </div>
      ) : null}
      {params.added ? (
        <div role="status" className={ui.cls("alert alert-success")}>
          Vendor added.
        </div>
      ) : null}
      <div className={ui.cls("toolbar")}>
        <form method="get" action="/vendors" role="search" style={{ display: "flex", gap: 6 }}>
          <input name="q" aria-label="Search vendors" defaultValue={q} placeholder="Vendor name" className={ui.cls("form-control")} style={{ width: 220 }} />
          <button type="submit" className={ui.cls("btn")}>
            {ui.t("search")}
          </button>
        </form>
        <span className={ui.cls("spacer")} />
        <AddVendorModal mutations={[...ui.mutations]} />
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>AP email</th>
            <th>City</th>
          </tr>
        </thead>
        <tbody>
          {vendors.map((v) => (
            <tr key={v.id}>
              <td>{v.id}</td>
              <td>{v.name}</td>
              <td>{v.email}</td>
              <td>{v.city || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
