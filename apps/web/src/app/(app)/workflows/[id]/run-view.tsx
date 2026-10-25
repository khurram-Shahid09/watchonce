"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import type { Secret, SpecInput, WorkflowSpec } from "@/lib/types";

import { saveSecret, startRun } from "../../actions";

const field =
  "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";

function initialValue(input: SpecInput): string | boolean {
  if (input.type === "boolean") return input.example === true;
  return input.example === undefined ? "" : String(input.example);
}

function LoginForm({ name, fields, canSave }: { name: string; fields: string[]; canSave: boolean }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  if (!canSave) {
    return (
      <p className="text-sm text-muted">
        Ask a workspace owner to save the <b>{name}</b> login.
      </p>
    );
  }
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        start(async () => {
          const result = await saveSecret(name, values);
          if (!result.ok) setError(result.message ?? "Couldn't save.");
        });
      }}
    >
      <div className="grid gap-2 sm:grid-cols-2">
        {fields.map((f) => (
          <label key={f} className="space-y-1">
            <span className="text-xs text-muted">{f.replace(/_/g, " ")}</span>
            <input
              className={field}
              type={/pass|secret|token|pin|code/.test(f) ? "password" : "text"}
              autoComplete="off"
              required
              value={values[f] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      <button disabled={pending} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-60">
        {pending ? "Saving…" : `Save ${name.replace(/_/g, " ")}`}
      </button>
      <p className="text-xs text-muted">Stored encrypted. Nobody can read it back, not even owners.</p>
    </form>
  );
}

export function RunView({
  workflowId,
  version,
  spec,
  secrets,
  isOwner,
  isActive,
}: {
  workflowId: string;
  version: number;
  spec: WorkflowSpec;
  secrets: Secret[];
  isOwner: boolean;
  isActive: boolean;
}) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(spec.inputs.map((i) => [i.name, initialValue(i)])),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const have = new Map(secrets.map((s) => [s.name, new Set(s.fields)]));
  const missing = spec.secrets.filter((s) => s.fields.some((f) => !have.get(s.name)?.has(f)));
  const checkpoints = spec.steps.filter((s) => s.checkpoint?.type === "approval").length;

  const submit = () =>
    start(async () => {
      setMessage(null);
      const inputs = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      const result = await startRun(workflowId, inputs, isActive ? undefined : version);
      if (result.ok && result.runId) {
        router.push(`/runs/${result.runId}`);
        return;
      }
      setErrors(result.inputErrors ?? {});
      setMessage(result.message ?? "Couldn't start the run.");
    });

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="space-y-4 rounded-lg border border-line bg-surface p-5">
        <div>
          <h3 className="font-medium">Run version {version}</h3>
          <p className="text-sm text-muted">
            A fresh browser does every step on {spec.allowed_domains.join(", ")}.
            {checkpoints > 0 && ` It stops for your approval ${checkpoints === 1 ? "once" : `${checkpoints} times`} before anything is submitted.`}
          </p>
        </div>
        {spec.inputs.length === 0 && <p className="text-sm text-muted">This workflow needs no inputs.</p>}
        {spec.inputs.map((input) => (
          <label key={input.name} className="block space-y-1">
            <span className="text-sm font-medium">
              {input.name.replace(/_/g, " ")}
              {input.required === false && <span className="font-normal text-muted"> (optional)</span>}
            </span>
            {input.type === "boolean" ? (
              <input
                type="checkbox"
                checked={values[input.name] === true}
                onChange={(e) => setValues((v) => ({ ...v, [input.name]: e.target.checked }))}
              />
            ) : (
              <input
                className={`${field} ${errors[input.name] ? "border-danger" : ""}`}
                type={input.type === "date" ? "date" : input.type === "number" || input.type === "integer" ? "number" : "text"}
                step={input.type === "number" ? "any" : undefined}
                value={String(values[input.name] ?? "")}
                onChange={(e) => setValues((v) => ({ ...v, [input.name]: e.target.value }))}
              />
            )}
            {input.description && <span className="block text-xs text-muted">{input.description}</span>}
            {errors[input.name] && <span className="block text-xs text-danger">{errors[input.name]}</span>}
          </label>
        ))}
        {message && (
          <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
            {message}
          </p>
        )}
        <button
          type="button"
          disabled={pending || missing.length > 0}
          onClick={submit}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {pending ? "Starting…" : "Run now"}
        </button>
      </section>

      <aside className="space-y-3">
        <div className="rounded-lg border border-line bg-surface p-4">
          <h3 className="text-sm font-medium">Saved logins</h3>
          {spec.secrets.length === 0 && <p className="mt-1 text-sm text-muted">None needed.</p>}
          <ul className="mt-2 space-y-3">
            {spec.secrets.map((s) => {
              const ok = !missing.includes(s);
              return (
                <li key={s.name} className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span>{s.name.replace(/_/g, " ")}</span>
                    <span className={ok ? "text-ok" : "text-warn"}>{ok ? "✓ saved" : "missing"}</span>
                  </div>
                  {!ok && <LoginForm name={s.name} fields={s.fields} canSave={isOwner} />}
                </li>
              );
            })}
          </ul>
        </div>
      </aside>
    </div>
  );
}
