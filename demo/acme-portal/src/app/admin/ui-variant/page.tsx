import type { Metadata } from "next";

import { getGlobalVariant, getVariant } from "@/lib/ui-server";
import { formatVariant, makeUi, MUTATION_INFO, MUTATIONS, PRESETS } from "@/lib/variant";

export const metadata: Metadata = { title: "UI variant (demo switch)" };

export default async function UiVariantPage({ searchParams }: PageProps<"/admin/ui-variant">) {
  const [current, params] = await Promise.all([getVariant(), searchParams]);
  const ui = makeUi(current.mutations);
  const global = getGlobalVariant();
  const tokenRequired = Boolean(process.env.ACME_ADMIN_TOKEN);

  return (
    <div className={ui.cls("card")}>
      <div className={ui.cls("card-title")}>UI variant: demo switch</div>
      {params.error ? (
        <div role="alert" className={ui.cls("alert alert-danger")}>
          {params.error === "token" ? "Wrong admin token." : "Unknown variant."}
        </div>
      ) : null}
      {params.saved ? (
        <div role="status" className={ui.cls("alert alert-success")}>
          Saved.
        </div>
      ) : null}
      <p>
        This page simulates the portal&apos;s IT team shipping a UI update, so WatchOnce&apos;s self-healing can be
        demonstrated. You are seeing <b>{formatVariant(current.mutations)}</b> (
        {current.source === "browser" ? "override for this browser only" : "portal-wide setting"}). Portal-wide
        setting: <b>{formatVariant(global)}</b>.
      </p>

      <form method="post" action="/admin/ui-variant/apply">
        <h2>Presets</h2>
        <div className={ui.cls("toolbar")}>
          {Object.keys(PRESETS).map((name) => (
            <button key={name} type="submit" name="preset" value={name} className={ui.cls("btn")}>
              {name === "v2" ? "Portal v2 (M1+M2+M3+M6+M7)" : "Original"}
            </button>
          ))}
        </div>

        <h2>Individual mutations</h2>
        <table>
          <tbody>
            {MUTATIONS.map((m) => (
              <tr key={m}>
                <td style={{ width: 30 }}>
                  <input
                    type="checkbox"
                    id={`mut-${m}`}
                    name="mutation"
                    value={m}
                    defaultChecked={current.mutations.includes(m)}
                  />
                </td>
                <td style={{ width: 160 }}>
                  <label htmlFor={`mut-${m}`}>
                    <b>{m.toUpperCase()}</b> {MUTATION_INFO[m].title}
                  </label>
                </td>
                <td>{MUTATION_INFO[m].description}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2 style={{ marginTop: 14 }}>Apply to</h2>
        <p>
          <label>
            <input type="radio" name="scope" value="global" defaultChecked /> Everyone (portal-wide, used by the
            WatchOnce runner)
          </label>
          <br />
          <label>
            <input type="radio" name="scope" value="browser" /> This browser only
          </label>
          <br />
          <label>
            <input type="radio" name="scope" value="reset" /> Remove this browser&apos;s override
          </label>
        </p>
        {tokenRequired ? (
          <p>
            <label>
              Admin token <input type="password" name="token" className={ui.cls("form-control")} style={{ width: 200 }} />
            </label>
          </p>
        ) : null}
        <button type="submit" className={ui.cls("btn btn-primary")}>
          Apply checked mutations
        </button>
      </form>
    </div>
  );
}
