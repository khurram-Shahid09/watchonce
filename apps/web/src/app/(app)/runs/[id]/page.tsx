import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { api, ApiError } from "@/lib/api";
import { FINISHED, type RunDetail, type Version } from "@/lib/types";

import { LiveRun } from "./live-run";

async function load<T>(path: string): Promise<T> {
  try {
    return await api<T>(path);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}

export default function RunPage(props: PageProps<"/runs/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading run…</p>}>
      <RunContent {...props} />
    </Suspense>
  );
}

async function RunContent({ params }: PageProps<"/runs/[id]">) {
  const { id } = await params;
  const run = await load<RunDetail>(`/runs/${encodeURIComponent(id)}`);
  const version = await load<Version>(`/workflows/${encodeURIComponent(run.workflow_id)}/versions/${run.version}`);
  const finished = FINISHED.includes(run.status);
  const when = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString("en", { dateStyle: "medium", timeStyle: "medium" }) : "–";

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/workflows/${run.workflow_id}?tab=runs`} className="text-sm text-muted hover:text-ink">
          ← {run.workflow_name}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Run {run.id.slice(-6)}</h1>
        <p className="mt-1 text-sm text-muted">
          Version {run.version} · started {when(run.started_at ?? run.created_at)}
          {run.finished_at && ` · finished ${when(run.finished_at)}`}
        </p>
      </div>

      {finished && (run.error_message || Object.keys(run.outputs).length > 0) && (
        <section className={`rounded-lg border p-4 ${run.status === "succeeded" ? "border-ok/40 bg-ok/5" : "border-danger/40 bg-danger/5"}`}>
          {run.error_message && <p className="text-sm text-danger">{run.error_message}</p>}
          {Object.keys(run.outputs).length > 0 && (
            <dl className="mt-1 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
              {Object.entries(run.outputs).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
                  <dd className="font-mono font-medium">{String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      )}

      <LiveRun key={`${run.id}-${run.status}`} initial={run} spec={version.spec} />

      <details className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">Inputs and history</summary>
        <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
          {Object.entries(run.inputs).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
              <dd>{String(v)}</dd>
            </div>
          ))}
        </dl>
        {run.decisions.length > 0 && (
          <ul className="mt-3 space-y-1">
            {run.decisions.map((d) => (
              <li key={d.step_id}>
                Step {d.step_id}: <b>{d.decision === "approve" ? "approved" : "rejected"}</b> by {d.decided_by ?? "someone"} at {when(d.created_at)}
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
