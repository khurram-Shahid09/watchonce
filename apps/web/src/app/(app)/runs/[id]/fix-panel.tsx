"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { startAuthoring } from "../../actions";

/** On a failed run: let the agent rebuild the workflow live from a hint, or edit the steps. */
export function FixPanel({ runId, workflowId, failedIntent }: { runId: string; workflowId: string; failedIntent?: string }) {
  const [hint, setHint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const fix = () =>
    start(async () => {
      setError(null);
      const result = await startAuthoring({ runId, instructions: hint.trim() || "Find what changed and complete the task." });
      if (result && !result.ok) setError(result.message ?? "Couldn't start the agent.");
    });

  return (
    <section className="space-y-3 rounded-lg border border-line bg-surface p-4">
      <div>
        <p className="font-semibold">Fix this workflow</p>
        <p className="text-sm text-muted">
          Tell the agent what to do differently{failedIntent ? ` at “${failedIntent}”` : ""}. It redoes the task live in a
          browser and saves the result as a new version (the current one is kept).
        </p>
      </div>
      <textarea
        rows={3}
        maxLength={4000}
        value={hint}
        onChange={(e) => setHint(e.target.value)}
        placeholder="e.g. The bill takes a few seconds to load: wait for “PAYABLE WITHIN DUE DATE”, then read the amount."
        className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm"
      />
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={fix} disabled={pending} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
          {pending ? "Starting…" : "Fix it with the agent"}
        </button>
        <Link href={`/workflows/${workflowId}?tab=edit`} className="text-sm text-accent hover:underline">
          or edit the steps yourself
        </Link>
      </div>
    </section>
  );
}
