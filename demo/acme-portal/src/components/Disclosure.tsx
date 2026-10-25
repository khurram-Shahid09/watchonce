"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { makeUi, type Mutation } from "@/lib/variant";

/** M4's "More ▾" menu: the moved toolbar actions only appear after an extra click. */
export function MoreMenu({ mutations, children }: { mutations: Mutation[]; children: ReactNode }) {
  const ui = makeUi(mutations);
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div className={ui.cls("dropdown")} style={{ width: "auto" }} ref={root}>
      <button type="button" className={ui.cls("btn")} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        More ▾
      </button>
      {open ? (
        <div role="menu" className={ui.cls("dropdown-menu")} style={{ left: "auto", minWidth: 180, padding: 6 }}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

/** "Add vendor" button + modal dialog with a classic form post. */
export function AddVendorModal({ mutations }: { mutations: Mutation[] }) {
  const ui = makeUi(mutations);
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        id={ui.id("btn-add-vendor")}
        className={ui.cls("btn btn-primary")}
        data-testid={ui.testid("add-vendor-btn")}
        onClick={() => setOpen(true)}
      >
        {ui.t("add_vendor")}
      </button>
      {open ? (
        <div className={ui.cls("modal-backdrop")}>
          <div role="dialog" aria-modal="true" aria-labelledby="add-vendor-title" className={ui.cls("modal")}>
            <div id="add-vendor-title" className={ui.cls("modal-title")}>
              {ui.t("add_vendor")}
            </div>
            <form method="post" action="/vendors/new" className={ui.cls("modal-body")}>
              <div className={ui.cls("form-grid")} style={{ gridTemplateColumns: "110px 1fr" }}>
                <label htmlFor="vendor-name" className={ui.cls("form-label")}>
                  Name
                </label>
                <input id="vendor-name" name="name" required maxLength={60} className={ui.cls("form-control")} autoFocus />
                <label htmlFor="vendor-email" className={ui.cls("form-label")}>
                  Email
                </label>
                <input id="vendor-email" name="email" type="email" required maxLength={80} className={ui.cls("form-control")} />
                <div className={ui.cls("form-actions")}>
                  <button type="submit" className={ui.cls("btn btn-primary")}>
                    Save vendor
                  </button>
                  <button type="button" className={ui.cls("btn")} onClick={() => setOpen(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
