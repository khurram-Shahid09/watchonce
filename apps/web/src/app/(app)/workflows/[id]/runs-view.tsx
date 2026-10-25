import Link from "next/link";

import { RunStatusBadge } from "@/components/run-status";
import type { Run } from "@/lib/types";

export function RunsList({ runs, showWorkflow = false }: { runs: Run[]; showWorkflow?: boolean }) {
  if (runs.length === 0) {
    return <p className="rounded-lg border border-dashed border-line bg-surface px-4 py-8 text-center text-sm text-muted">No runs yet.</p>;
  }
  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
      {runs.map((run) => (
        <li key={run.id}>
          <Link href={`/runs/${run.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-canvas">
            <div className="min-w-0">
              <div className="font-medium">
                {showWorkflow ? run.workflow_name : `Run ${run.id.slice(-6)}`}{" "}
                <span className="text-sm font-normal text-muted">v{run.version}</span>
              </div>
              <div className="truncate text-sm text-muted">
                {new Date(run.created_at).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" })}
                {Object.keys(run.outputs).length > 0 && ` · ${Object.entries(run.outputs).map(([k, v]) => `${k}: ${String(v)}`).join(", ")}`}
                {run.error_message && ` · ${run.error_message}`}
              </div>
            </div>
            <RunStatusBadge status={run.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
