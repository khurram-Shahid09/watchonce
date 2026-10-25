import Link from "next/link";

import { ActionButton } from "@/components/client-bits";
import { screenshotUrl } from "@/lib/steps";
import type { Heal } from "@/lib/types";

import { decideHeal } from "../../actions";

const RUNG: Record<Heal["rung"], string> = {
  L2: "Found by similarity",
  L3: "Found by AI",
};

const DECISION_STYLE: Record<Heal["decision"], string> = {
  pending: "bg-warn-soft text-warn",
  approved: "bg-ok/15 text-ok",
  auto: "bg-ok/15 text-ok",
  rejected: "bg-danger/10 text-danger",
};

function locatorText(l: Heal["after_locators"][number]): string {
  return l.kind === "role" ? `${l.role} “${l.name ?? ""}”` : `${l.kind}: ${l.value ?? ""}`;
}

export function HealsView({ workflowId, heals, isOwner }: { workflowId: string; heals: Heal[]; isOwner: boolean }) {
  if (heals.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-line bg-surface px-4 py-8 text-center text-sm text-muted">
        No self-heals yet. When the website changes and a step can&apos;t find its button or field, WatchOnce finds it
        again and asks you here before changing the workflow.
      </p>
    );
  }
  // All fixes from one run are saved together as one new version: decide them together.
  const groups = new Map<string, Heal[]>();
  for (const h of heals) {
    const key = h.resulting_version ? `v${h.resulting_version.version}` : h.id;
    groups.set(key, [...(groups.get(key) ?? []), h]);
  }
  return (
    <div className="space-y-8">
      {[...groups.values()].map((group) => {
        const first = group[0]!;
        const pending = group.some((h) => h.decision === "pending");
        return (
          <section key={first.id} className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3">
              <div>
                <p className="font-medium">
                  {group.length} fix{group.length === 1 ? "" : "es"} from run{" "}
                  <Link href={`/runs/${first.run_id}`} className="text-accent hover:underline">
                    {first.run_id.slice(-6)}
                  </Link>
                  {first.resulting_version && ` → version ${first.resulting_version.version}`}
                </p>
                <p className="text-sm text-muted">
                  {pending
                    ? "Approving makes this version the one that runs. Rejecting keeps the current version."
                    : `${first.decision === "auto" ? "Applied automatically" : first.decision}${first.decided_by ? ` by ${first.decided_by}` : ""}.`}
                </p>
              </div>
              {pending && isOwner && (
                <div className="flex gap-2">
                  <ActionButton
                    action={decideHeal.bind(null, first.id, "approve")}
                    label={group.length === 1 ? "Approve fix" : `Approve all ${group.length} fixes`}
                    className="rounded-md bg-ok px-3 py-1.5 text-sm font-semibold text-white"
                  />
                  <ActionButton
                    action={decideHeal.bind(null, first.id, "reject")}
                    label="Reject"
                    className="rounded-md border border-danger px-3 py-1.5 text-sm text-danger"
                  />
                </div>
              )}
              {pending && !isOwner && <p className="text-xs text-muted">A workspace owner approves fixes.</p>}
            </div>
    <ul className="space-y-4">
      {group.map((h) => (
        <li key={h.id} className="space-y-3 rounded-lg border border-line bg-surface p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{h.step_intent}</span>
                <span className="rounded bg-canvas px-1.5 py-0.5 text-xs text-muted">{RUNG[h.rung]}</span>
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${DECISION_STYLE[h.decision]}`}>{h.decision}</span>
              </div>
              <p className="mt-1 text-sm">{h.explanation}</p>
              <p className="mt-1 text-xs text-muted">
                Similarity {(h.score * 100).toFixed(0)}%
                {h.model_confidence !== null && ` · AI confidence ${(h.model_confidence * 100).toFixed(0)}%`}
                {" · "}
                <Link href={`/runs/${h.run_id}`} className="text-accent hover:underline">
                  run {h.run_id.slice(-6)}
                </Link>
                {h.resulting_version && ` · saved as version ${h.resulting_version.version} (${h.resulting_version.status.replace("_", " ")})`}
                {h.decided_by && ` · ${h.decision} by ${h.decided_by}`}
              </p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <figure className="space-y-1">
              <figcaption className="text-xs text-muted">When recorded</figcaption>
              {h.before_image_ref ? (
                // eslint-disable-next-line @next/next/no-img-element -- short-lived storage links
                <img src={screenshotUrl(workflowId, h.before_image_ref)} alt="Page when recorded" className="rounded-md border border-line" />
              ) : (
                <p className="text-xs text-muted">No screenshot</p>
              )}
              <p className="text-xs text-muted">Looked for: {h.before_locators.slice(0, 2).map(locatorText).join(" · ")}</p>
            </figure>
            <figure className="space-y-1">
              <figcaption className="text-xs text-muted">Now (the element it found is outlined)</figcaption>
              {h.after_image_ref ? (
                // eslint-disable-next-line @next/next/no-img-element -- short-lived storage links
                <img
                  src={`/bff/runs/${encodeURIComponent(h.run_id)}/screenshots/${encodeURIComponent(h.after_image_ref)}`}
                  alt="Page now, healed element outlined"
                  className="rounded-md border border-line"
                />
              ) : (
                <p className="text-xs text-muted">No screenshot</p>
              )}
              <p className="text-xs text-muted">Will look for: {h.after_locators.slice(0, 2).map(locatorText).join(" · ")}</p>
            </figure>
          </div>
        </li>
      ))}
    </ul>
          </section>
        );
      })}
    </div>
  );
}
