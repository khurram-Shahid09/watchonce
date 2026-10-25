import type { Metadata } from "next";

import { Field } from "@/components/Wrap";
import { DEMO_USER } from "@/lib/session";
import { getUi } from "@/lib/ui-server";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const ui = await getUi();
  const { error } = await searchParams;

  return (
    <div className={ui.cls("login-box")}>
      <div className={ui.cls("card")}>
        <div className={ui.cls("card-title")}>Sign in to Acme Vendor Portal</div>
        {error ? (
          <div role="alert" className={ui.cls("alert alert-danger")}>
            Invalid username or password.
          </div>
        ) : null}
        <form method="post" action="/login/submit" id="login-form">
          <div className={ui.cls("form-grid")} style={{ gridTemplateColumns: "90px 1fr" }}>
            <Field ui={ui} id={ui.id("username")} label={ui.t("username")}>
              <input
                id={ui.id("username")}
                name="username"
                autoComplete="username"
                required
                className={ui.cls("form-control")}
                data-testid={ui.testid("login-username")}
              />
            </Field>
            <Field ui={ui} id={ui.id("password")} label={ui.t("password")}>
              <input
                id={ui.id("password")}
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className={ui.cls("form-control")}
                data-testid={ui.testid("login-password")}
              />
            </Field>
            <div className={ui.cls("form-actions")}>
              <button
                type="submit"
                id={ui.id("btn-login")}
                className={ui.cls("btn btn-primary")}
                data-testid={ui.testid("login-submit")}
              >
                {ui.t("sign_in")}
              </button>
            </div>
          </div>
        </form>
      </div>
      <p className={ui.cls("muted")}>
        Demo account: <b>{DEMO_USER.username}</b> / <b>{DEMO_USER.password}</b> (fake data only).
      </p>
    </div>
  );
}
