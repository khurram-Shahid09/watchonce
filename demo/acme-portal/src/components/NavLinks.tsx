"use client";

import { usePathname } from "next/navigation";

import { makeUi, type Mutation } from "@/lib/variant";

const LINKS = [
  ["/dashboard", "Dashboard"],
  ["/invoices", "Invoices"],
  ["/vendors", "Vendors"],
  ["/approvals", "Approvals"],
] as const;

export function NavLinks({ mutations }: { mutations: Mutation[] }) {
  const ui = makeUi(mutations);
  const pathname = usePathname();
  return (
    <nav className={ui.cls("nav")}>
      {LINKS.map(([href, label]) => (
        <a
          key={href}
          href={href}
          className={ui.cls(pathname.startsWith(href) ? "nav-link active" : "nav-link")}
          aria-current={pathname.startsWith(href) ? "page" : undefined}
        >
          {label}
        </a>
      ))}
    </nav>
  );
}
