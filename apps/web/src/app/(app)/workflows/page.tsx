import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { ActionButton, AutoRefresh } from "@/components/client-bits";
import { api, ApiError } from "@/lib/api";
import type { Page, Recording, Workflow } from "@/lib/types";

import { recompile } from "../actions";

export const metadata: Metadata = { title: "Workflows" };

const STATUS_TEXT: Record<Recording["status"], string> = {
  uploading: "Uploading…",
  uploaded: "Waiting to compile…",
  compiling: "Compiling with AI…",
  compiled: "Compiled",
  failed: "Failed",
};

function when(iso: string): string {
  return new Date(iso).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" });
}

export default function WorkflowsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Workflows</h1>
        <p className="mt-1 text-sm text-muted">
          Record a task with the WatchOnce Chrome extension; it shows up here as a workflow.
        </p>
      </div>
      <Suspense fallback={<p className="text-sm text-muted">Loading workflows…</p>}>
        <WorkflowList />
      </Suspense>
    </div>
  );
}

async function WorkflowList() {
  let workflows: Page<Workflow>, recordings: Page<Recording>;
  try {
    [workflows, recordings] = await Promise.all([
      api<Page<Workflow>>("/workflows?limit=100"),
      api<Page<Recording>>("/recordings?limit=20"),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.code === "no_organization") {
      return (
        <p className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
          Your account isn&apos;t in a workspace yet. Create one by signing up, or ask a workspace owner to add you.
        </p>
      );
    }
    throw err;
  }
  const pending = recordings.results.filter((r) => r.status !== "compiled");
  const busy = pending.some((r) => ["uploading", "uploaded", "compiling"].includes(r.status));

  return (
    <div className="space-y-8">
      {busy && <AutoRefresh />}
      {pending.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium text-muted">Recordings in progress</h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {pending.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate font-medium">{r.description || "Untitled recording"}</div>
                  <div className="text-xs text-muted">
                    {r.event_count} actions · {r.frame_count} screenshots · {when(r.created_at)}
                  </div>
                  {r.status === "failed" && <p className="mt-1 text-sm text-danger">{r.error}</p>}
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-sm ${r.status === "failed" ? "text-danger" : "text-muted"}`}>
                    {STATUS_TEXT[r.status]}
                  </span>
                  {r.status === "failed" && (
                    <ActionButton action={recompile.bind(null, r.id)} label="Compile again" pendingLabel="Queued…" />
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {workflows.results.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line bg-surface px-6 py-12 text-center">
          <p className="font-medium">No workflows yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted">
            Install the recorder, connect it to this workspace with an access token, then do the task once
            while it records. WatchOnce turns it into a workflow and an SOP.
          </p>
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {workflows.results.map((w) => (
            <li key={w.id}>
              <Link
                href={`/workflows/${w.id}`}
                className="block h-full rounded-lg border border-line bg-surface p-4 transition hover:border-accent/60 hover:shadow-sm"
              >
                <div className="font-medium">{w.name}</div>
                {w.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{w.description}</p>}
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                  <span>{w.step_count} steps</span>
                  <span>{w.input_count} inputs</span>
                  {w.active_version && <span>v{w.active_version.version} active</span>}
                  <span>Updated {when(w.updated_at)}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
