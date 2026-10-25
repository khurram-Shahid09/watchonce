import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { ActionButton, AutoRefresh } from "@/components/client-bits";
import { RunStatusBadge } from "@/components/run-status";
import { api, ApiError } from "@/lib/api";
import type { BatchDetail, Me } from "@/lib/types";

import { approveAllBatch, cancelBatch } from "../../actions";

export const metadata: Metadata = { title: "Batch" };

export default function BatchPage(props: PageProps<"/batches/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading batch…</p>}>
      <BatchContent {...props} />
    </Suspense>
  );
}

async function BatchContent({ params }: PageProps<"/batches/[id]">) {
  const { id } = await params;
  let batch: BatchDetail;
  try {
    batch = await api<BatchDetail>(`/batches/${encodeURIComponent(id)}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const me = await api<Me>("/me");
  const isOwner = me.memberships[0]?.role === "owner";
  const active = batch.status === "queued" || batch.status === "running";
  const done = batch.succeeded + batch.failed;
  const waiting = batch.runs.find((r) => r.status === "awaiting_approval");
  const runs = [...batch.runs].sort((a, b) => a.row_index - b.row_index);
  const outputNames = [...new Set(runs.flatMap((r) => Object.keys(r.outputs)))];

  return (
    <div className="space-y-6">
      {active && <AutoRefresh everyMs={3000} />}
      <div>
        <Link href={`/workflows/${batch.workflow_id}?tab=batch`} className="text-sm text-muted hover:text-ink">
          ← {batch.workflow_name}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Batch: {batch.file_name || batch.id.slice(-6)}</h1>
        <p className="mt-1 text-sm text-muted">
          Version {batch.version} · {batch.total} rows · {batch.status}
          {batch.approve_all && batch.approved_by && ` · approvals given for the whole batch by ${batch.approved_by}`}
        </p>
      </div>

      <section className="space-y-3 rounded-lg border border-line bg-surface p-4">
        <div className="h-2 overflow-hidden rounded-full bg-canvas">
          <div className="flex h-full">
            <div className="bg-ok" style={{ width: `${(batch.succeeded / batch.total) * 100}%` }} />
            <div className="bg-danger" style={{ width: `${(batch.failed / batch.total) * 100}%` }} />
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <span>
            {done} of {batch.total} done · <span className="text-ok">{batch.succeeded} succeeded</span> ·{" "}
            <span className="text-danger">{batch.failed} failed</span>
          </span>
          <div className="flex flex-wrap gap-2">
            {active && (
              <ActionButton action={cancelBatch.bind(null, batch.id)} label="Cancel batch" confirm="Stop the remaining rows?" />
            )}
            <a href={`/bff/batches/${batch.id}/results`} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas">
              Download results CSV
            </a>
          </div>
        </div>
      </section>

      {waiting && !batch.approve_all && (
        <section className="space-y-2 rounded-lg border-2 border-warn bg-warn-soft p-4">
          <p className="font-semibold text-warn">Row {waiting.row_index} is waiting for approval.</p>
          <p className="text-sm">
            Review it on its run page and approve or reject it there.
            {isOwner && " Once you have checked it, you can approve this step for every remaining row at once."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href={`/runs/${waiting.id}`} className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-white">
              Review row {waiting.row_index}
            </Link>
            {isOwner && (
              <ActionButton
                action={approveAllBatch.bind(null, batch.id)}
                label="Approve for all rows"
                confirm="Approve every checkpoint of this batch, for all remaining rows? This is recorded in the audit log."
                className="rounded-md border border-warn px-3 py-1.5 text-sm font-semibold text-warn"
              />
            )}
          </div>
        </section>
      )}

      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-canvas text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2">Row</th>
              {batch.columns.map((c) => (
                <th key={c} className="px-3 py-2">
                  {c}
                </th>
              ))}
              <th className="px-3 py-2">Status</th>
              {outputNames.map((o) => (
                <th key={o} className="px-3 py-2">
                  {o.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {runs.map((r) => (
              <tr key={r.id}>
                <td className="px-3 py-2">
                  <Link href={`/runs/${r.id}`} className="text-accent hover:underline">
                    {r.row_index}
                  </Link>
                </td>
                {batch.columns.map((c) => {
                  const input = Object.entries(batch.column_map).find(([, col]) => col === c)?.[0];
                  return (
                    <td key={c} className="px-3 py-2">
                      {input ? String(r.inputs[input] ?? "") : <span className="text-muted">–</span>}
                    </td>
                  );
                })}
                <td className="px-3 py-2">
                  <RunStatusBadge status={r.status} />
                  {r.error_message && <div className="mt-1 max-w-xs truncate text-xs text-danger" title={r.error_message}>{r.error_message}</div>}
                </td>
                {outputNames.map((o) => (
                  <td key={o} className="px-3 py-2 font-mono">
                    {String(r.outputs[o] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
