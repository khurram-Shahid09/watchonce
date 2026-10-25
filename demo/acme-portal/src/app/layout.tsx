import type { Metadata } from "next";

import { NavLinks } from "@/components/NavLinks";
import { getSession } from "@/lib/session";
import { stylesheet } from "@/lib/styles";
import { getVariant } from "@/lib/ui-server";
import { formatVariant, makeUi } from "@/lib/variant";

export const metadata: Metadata = {
  title: { default: "Acme Vendor Portal", template: "%s - Acme Vendor Portal" },
  description: "Demo vendor portal for WatchOnce (fake data).",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const [session, variant] = await Promise.all([getSession(), getVariant()]);
  const ui = makeUi(variant.mutations);

  return (
    <html lang="en">
      <head>
        <style dangerouslySetInnerHTML={{ __html: stylesheet(ui) }} />
      </head>
      <body>
        <header className={ui.cls("header")}>
          <a href={session ? "/dashboard" : "/login"} className={ui.cls("brand")}>
            ACME Vendor Portal<small>v4.2</small>
          </a>
          {session ? (
            <>
              <NavLinks mutations={variant.mutations} />
              <div className={ui.cls("userbox")}>
                <span>Signed in as {session.user}</span>
                <form method="post" action="/logout">
                  <button type="submit" className={ui.cls("btn btn-sm")}>
                    Sign out
                  </button>
                </form>
              </div>
            </>
          ) : null}
        </header>
        <main className={ui.cls("container")}>{children}</main>
        <footer className={ui.cls("footer")}>
          <span>© Acme Corp. Demo system with fake data, built for WatchOnce.</span>
          <a href="/admin/ui-variant" className={ui.cls("muted")}>
            UI: {formatVariant(variant.mutations)}
          </a>
        </footer>
      </body>
    </html>
  );
}
