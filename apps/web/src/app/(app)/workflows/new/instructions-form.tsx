"use client";

import { useState, useTransition } from "react";

import { saveSecret, startAuthoring } from "../../actions";

const EXAMPLE = `Search for my MEPCO bill with reference number 01234567890123
Wait for the bill to load
Read the amount payable within due date as bill_amount
Read the due date as due_date`;

export function InstructionsForm({ logins }: { logins: { name: string; fields: string[] }[] }) {
  const [startUrl, setStartUrl] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, start] = useTransition();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    start(async () => {
      const result = await startAuthoring({ startUrl: startUrl.trim(), instructions: instructions.trim() });
      if (result && !result.ok) {
        setError(result.message ?? "Couldn't start.");
        setFieldErrors(result.fieldErrors ?? {});
      }
    });
  };

  return (
    <form onSubmit={submit} className="space-y-5 rounded-lg border border-line bg-surface p-5">
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Start at this link</span>
        <input
          type="url"
          required
          value={startUrl}
          onChange={(e) => setStartUrl(e.target.value)}
          placeholder="https://bill.pitc.com.pk/mepcobill"
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm"
        />
        {fieldErrors.start_url && <span className="text-xs text-danger">{fieldErrors.start_url.join(" ")}</span>}
      </label>

      <label className="block space-y-1.5">
        <span className="text-sm font-medium">What should it do?</span>
        <textarea
          required
          rows={9}
          maxLength={8000}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder={EXAMPLE}
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 font-mono text-sm leading-relaxed"
        />
        {fieldErrors.instructions && <span className="text-xs text-danger">{fieldErrors.instructions.join(" ")}</span>}
      </label>

      <div className="space-y-2 rounded-md bg-canvas px-4 py-3 text-sm">
        <p className="font-medium">Tips</p>
        <ul className="list-disc space-y-1 pl-5 text-muted">
          <li>One step per line works best. Say what to read (&ldquo;Read the total as total_amount&rdquo;).</li>
          <li>Values that change each time (names, amounts, reference numbers) become inputs you fill in per run.</li>
          <li>Anything that submits, pays, deletes or posts stops and asks you before it&apos;s clicked.</li>
          <li>
            Never type a password here. Say &ldquo;log in with my saved login <i>name</i>&rdquo; instead
            {logins.length > 0 ? ":" : " (save one below)."}
          </li>
        </ul>
        {logins.length > 0 && (
          <ul className="flex flex-wrap gap-2 pt-1">
            {logins.map((l) => (
              <li key={l.name} className="rounded border border-line bg-surface px-2 py-0.5 font-mono text-xs">
                {l.name} <span className="text-muted">({l.fields.join(", ")})</span>
              </li>
            ))}
          </ul>
        )}
        <SaveLogin />
      </div>

      {error && <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      <button type="submit" disabled={pending} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
        {pending ? "Starting…" : "Build it live"}
      </button>
    </form>
  );
}

/** Save a login in the vault (encrypted; never shown again, never sent to the AI). */
function SaveLogin() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, start] = useTransition();

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-sm text-accent hover:underline">
        + Save a login
      </button>
    );
  }
  const save = () =>
    start(async () => {
      const result = await saveSecret(name.trim(), { username, password });
      if (result.ok) {
        setMessage(`Saved. Use it as: log in with my saved login ${name.trim()}`);
        setUsername("");
        setPassword("");
      } else setMessage(result.message ?? "Couldn't save.");
    });
  return (
    <div className="grid gap-2 border-t border-line pt-3 sm:grid-cols-3">
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="name, e.g. petx_login" className="rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-xs" />
      <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username or email" autoComplete="off" className="rounded-md border border-line bg-surface px-2 py-1.5 text-xs" />
      <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" type="password" autoComplete="new-password" className="rounded-md border border-line bg-surface px-2 py-1.5 text-xs" />
      <div className="flex items-center gap-3 sm:col-span-3">
        <button type="button" disabled={pending || !name || !password} onClick={save} className="rounded-md border border-line bg-surface px-3 py-1 text-xs font-medium disabled:opacity-50">
          {pending ? "Saving…" : "Save login"}
        </button>
        {message && <span className="text-xs text-muted">{message}</span>}
      </div>
    </div>
  );
}
