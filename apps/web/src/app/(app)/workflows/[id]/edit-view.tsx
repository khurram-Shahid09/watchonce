"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { ACTION_LABEL } from "@/lib/steps";
import type { SpecInput, Step, WorkflowSpec } from "@/lib/types";

import { saveVersion, type SaveResult } from "../../actions";

const field =
  "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";
const INPUT_TYPES: SpecInput["type"][] = ["string", "number", "integer", "boolean", "date"];
const IDENT = /^[a-z][a-z0-9_]{0,63}$/;

function typedExample(type: SpecInput["type"], raw: string): SpecInput["example"] {
  if (raw === "") return undefined;
  if ((type === "number" || type === "integer") && !Number.isNaN(Number(raw))) return Number(raw);
  if (type === "boolean") return ["true", "yes", "1"].includes(raw.toLowerCase());
  return raw;
}

function renameRefs(text: string, from: string, to: string): string {
  return text.replace(new RegExp(`\\{\\{\\s*${from}(\\s*[|}])`, "g"), `{{${to}$1`);
}

/** "steps/3/value" → "Step 4"; everything else stays as the validator wrote it. */
function where(path: string): string {
  const m = /^steps\/(\d+)/.exec(path);
  if (m) return `Step ${Number(m[1]) + 1}`;
  const i = /^inputs\/(\d+)/.exec(path);
  return i ? `Input ${Number(i[1]) + 1}` : path || "Workflow";
}

export function EditView({
  workflowId,
  baseVersion,
  initial,
  canActivate,
}: {
  workflowId: string;
  baseVersion: number;
  initial: WorkflowSpec;
  canActivate: boolean;
}) {
  const router = useRouter();
  const [spec, setSpec] = useState<WorkflowSpec>(() => structuredClone(initial));
  const [note, setNote] = useState("");
  const [activate, setActivate] = useState(canActivate);
  const [result, setResult] = useState<SaveResult | null>(null);
  const [pending, start] = useTransition();
  const dirty = useMemo(() => JSON.stringify(spec) !== JSON.stringify(initial), [spec, initial]);

  const update = (fn: (draft: WorkflowSpec) => void) =>
    setSpec((prev) => {
      const next = structuredClone(prev);
      fn(next);
      return next;
    });

  const setStep = (index: number, fn: (step: Step) => void) => update((d) => fn(d.steps[index]!));

  const renameInput = (index: number, name: string) =>
    update((d) => {
      const old = d.inputs[index]!.name;
      d.inputs[index]!.name = name;
      if (!IDENT.test(name) || !IDENT.test(old)) return;
      for (const step of d.steps) {
        if ("value" in step && typeof step.value === "string") step.value = renameRefs(step.value, old, name);
        if ("label" in step && typeof step.label === "string") step.label = renameRefs(step.label, old, name);
        if (step.action === "navigate") step.url = renameRefs(step.url, old, name);
      }
    });

  const save = () =>
    start(async () => {
      const outcome = await saveVersion(workflowId, spec, note, baseVersion, activate);
      setResult(outcome);
      if (outcome.ok && outcome.version) router.push(`/workflows/${workflowId}?v=${outcome.version}`);
    });

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-line bg-surface p-4">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Name</span>
          <input className={field} value={spec.name} onChange={(e) => update((d) => void (d.name = e.target.value))} />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Description</span>
          <textarea
            className={field}
            rows={2}
            value={spec.description ?? ""}
            onChange={(e) => update((d) => void (d.description = e.target.value))}
          />
        </label>
      </section>

      <section className="rounded-lg border border-line bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium">Inputs</h3>
        {spec.inputs.length === 0 && <p className="text-sm text-muted">This workflow takes no inputs.</p>}
        <div className="space-y-3">
          {spec.inputs.map((input, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_110px_1.4fr_1fr_auto] sm:items-end">
              <label className="space-y-1">
                <span className="text-xs text-muted">Name</span>
                <input
                  className={`${field} font-mono ${IDENT.test(input.name) ? "" : "border-danger"}`}
                  value={input.name}
                  onChange={(e) => renameInput(i, e.target.value)}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-muted">Type</span>
                <select
                  className={field}
                  value={input.type}
                  onChange={(e) => update((d) => void (d.inputs[i]!.type = e.target.value as SpecInput["type"]))}
                >
                  {INPUT_TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-muted">Description</span>
                <input
                  className={field}
                  value={input.description ?? ""}
                  onChange={(e) => update((d) => void (d.inputs[i]!.description = e.target.value))}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-muted">Example</span>
                <input
                  className={field}
                  value={input.example === undefined ? "" : String(input.example)}
                  onChange={(e) =>
                    update((d) => {
                      const example = typedExample(d.inputs[i]!.type, e.target.value);
                      if (example === undefined) delete d.inputs[i]!.example;
                      else d.inputs[i]!.example = example;
                    })
                  }
                />
              </label>
              <label className="flex items-center gap-1.5 pb-2 text-sm">
                <input
                  type="checkbox"
                  checked={input.required !== false}
                  onChange={(e) => update((d) => void (d.inputs[i]!.required = e.target.checked))}
                />
                Required
              </label>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-medium">Steps</h3>
        {spec.steps.map((step, i) => {
          const valueKey = step.action === "fill" ? "value" : step.action === "select" ? ("label" in step ? "label" : "value") : null;
          const checkpoint = step.checkpoint?.type === "approval";
          return (
            <div key={step.id} className={`space-y-2 rounded-lg border bg-surface p-4 ${checkpoint ? "border-warn/60" : "border-line"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted">
                  Step {i + 1} · {ACTION_LABEL[step.action]}
                </span>
                {i > 0 && (
                  <button
                    type="button"
                    className="text-xs text-muted hover:text-danger"
                    onClick={() => update((d) => void d.steps.splice(i, 1))}
                  >
                    Remove step
                  </button>
                )}
              </div>
              <input
                className={field}
                value={step.intent}
                aria-label={`Step ${i + 1} intent`}
                onChange={(e) => setStep(i, (s) => void (s.intent = e.target.value))}
              />
              {valueKey && (
                <label className="block space-y-1">
                  <span className="text-xs text-muted">
                    {valueKey === "label" ? "Option to choose" : "Value"} (use {"{{input_name}}"} for inputs)
                  </span>
                  <input
                    className={`${field} font-mono`}
                    value={String((step as Record<string, unknown>)[valueKey] ?? "")}
                    onChange={(e) => setStep(i, (s) => void ((s as Record<string, unknown>)[valueKey] = e.target.value))}
                  />
                </label>
              )}
              {step.action !== "navigate" && (
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={checkpoint}
                      onChange={(e) =>
                        setStep(i, (s) => {
                          if (e.target.checked) s.checkpoint = { type: "approval", reason: "Review before this step runs." };
                          else delete s.checkpoint;
                        })
                      }
                    />
                    Ask for approval before this step
                  </label>
                  {checkpoint && (
                    <input
                      className={`${field} max-w-md flex-1`}
                      placeholder="Why it needs approval"
                      value={step.checkpoint?.reason ?? ""}
                      onChange={(e) => setStep(i, (s) => void (s.checkpoint = { type: "approval", reason: e.target.value }))}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </section>

      <section className="sticky bottom-0 space-y-3 rounded-lg border border-line bg-surface p-4 shadow-lg">
        {result && !result.ok && (
          <div role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
            <p className="font-medium">{result.message}</p>
            {result.errors && result.errors.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {result.errors.map((e, n) => (
                  <li key={n}>
                    {where(e.path)}: {e.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <input
            className={`${field} min-w-56 flex-1`}
            placeholder="What changed? (optional)"
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
          />
          {canActivate && (
            <label className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
              Make it the active version
            </label>
          )}
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-50"
            disabled={!dirty || pending}
            onClick={() => {
              setSpec(structuredClone(initial));
              setResult(null);
            }}
          >
            Discard
          </button>
          <button
            type="button"
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
            disabled={!dirty || pending}
            onClick={save}
          >
            {pending ? "Saving…" : "Save as new version"}
          </button>
        </div>
        <p className="text-xs text-muted">Saved versions never change; every save adds a version you can go back to.</p>
      </section>
    </div>
  );
}
