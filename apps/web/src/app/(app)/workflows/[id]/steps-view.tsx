import { ACTION_LABEL, screenshotUrl, stepDetail, templateParts } from "@/lib/steps";
import type { Version } from "@/lib/types";

function Template({ text }: { text: string }) {
  return (
    <>
      {templateParts(text).map((part, i) =>
        part.ref ? (
          <code key={i} className="rounded bg-accent/10 px-1 py-0.5 font-mono text-[0.8em] text-accent">
            {part.text}
          </code>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  );
}

export function StepsView({ workflowId, version }: { workflowId: string; version: Version }) {
  const { spec } = version;
  return (
    <div className="space-y-6">
      {version.warnings.length > 0 && (
        <details className="rounded-lg border border-warn/40 bg-warn-soft px-4 py-3 text-sm">
          <summary className="cursor-pointer font-medium text-warn">
            {version.warnings.length} thing{version.warnings.length === 1 ? "" : "s"} to review
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {version.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-line bg-surface p-4 md:col-span-2">
          <h3 className="text-sm font-medium text-muted">Inputs (asked for on every run)</h3>
          {spec.inputs.length === 0 ? (
            <p className="mt-2 text-sm">None</p>
          ) : (
            <ul className="mt-2 space-y-1.5 text-sm">
              {spec.inputs.map((i) => (
                <li key={i.name} className="flex flex-wrap gap-x-2">
                  <code className="font-mono text-accent">{i.name}</code>
                  <span className="text-muted">{i.type}</span>
                  {i.description && <span>· {i.description}</span>}
                  {i.example !== undefined && <span className="text-muted">· e.g. {String(i.example)}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-3 rounded-lg border border-line bg-surface p-4 text-sm">
          <div>
            <h3 className="font-medium text-muted">Saved logins</h3>
            <p className="mt-1">
              {spec.secrets.length ? spec.secrets.map((s) => `${s.name} (${s.fields.join(", ")})`).join("; ") : "None"}
            </p>
          </div>
          <div>
            <h3 className="font-medium text-muted">Outputs</h3>
            <p className="mt-1">{spec.outputs.length ? spec.outputs.map((o) => o.name).join(", ") : "None"}</p>
          </div>
          <div>
            <h3 className="font-medium text-muted">Allowed sites</h3>
            <p className="mt-1 break-all">{spec.allowed_domains.join(", ")}</p>
          </div>
        </div>
      </section>

      <ol className="space-y-3">
        {spec.steps.map((step, n) => {
          const detail = stepDetail(step);
          const checkpoint = step.checkpoint?.type === "approval" ? step.checkpoint : null;
          const locators = "target" in step && step.target ? step.target.locators : [];
          return (
            <li
              key={step.id}
              className={`grid gap-4 rounded-lg border bg-surface p-4 md:grid-cols-[1fr_minmax(0,360px)] ${checkpoint ? "border-warn/60" : "border-line"}`}
            >
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-canvas text-xs font-semibold">
                    {n + 1}
                  </span>
                  <span className="rounded bg-canvas px-1.5 py-0.5 text-xs text-muted">{ACTION_LABEL[step.action]}</span>
                  {checkpoint && (
                    <span className="rounded bg-warn-soft px-1.5 py-0.5 text-xs font-medium text-warn">
                      Needs approval
                    </span>
                  )}
                </div>
                <p className="font-medium">{step.intent}</p>
                {detail && (
                  <p className="break-all text-sm">
                    <Template text={detail} />
                  </p>
                )}
                {checkpoint?.reason && <p className="text-sm text-warn">⚠ {checkpoint.reason}</p>}
                {"assert_after" in step && step.assert_after && (
                  <p className="text-xs text-muted">
                    Then checks {step.assert_after.type.replace("_", " ")}
                    {"value" in step.assert_after ? `: “${step.assert_after.value}”` : ""}
                  </p>
                )}
                {locators.length > 0 && (
                  <details className="text-xs text-muted">
                    <summary className="cursor-pointer">How it finds the element ({locators.length} ways)</summary>
                    <ol className="mt-1 list-decimal space-y-0.5 pl-5 font-mono">
                      {locators.map((loc, i) => (
                        <li key={i} className="break-all">
                          {loc.kind}: {"role" in loc ? `${loc.role} “${loc.name ?? ""}”` : loc.value}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </div>
              {step.screenshot_ref ? (
                // eslint-disable-next-line @next/next/no-img-element -- short-lived storage links, not optimizable
                <img
                  src={screenshotUrl(workflowId, step.screenshot_ref)}
                  alt={`Screen before step ${n + 1}`}
                  loading="lazy"
                  className="w-full rounded-md border border-line"
                />
              ) : (
                <div className="hidden items-center justify-center rounded-md border border-dashed border-line text-xs text-muted md:flex">
                  No screenshot
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
