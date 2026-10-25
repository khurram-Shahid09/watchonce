import type { Metadata } from "next";
import { Suspense } from "react";

import { AutoRefresh } from "@/components/client-bits";
import { api } from "@/lib/api";
import { FINISHED, type Page, type Run } from "@/lib/types";

import { RunsList } from "../workflows/[id]/runs-view";

export const metadata: Metadata = { title: "Runs" };

async function AllRuns() {
  const runs = (await api<Page<Run>>("/runs?limit=50")).results;
  const busy = runs.some((r) => !FINISHED.includes(r.status));
  return (
    <>
      {busy && <AutoRefresh everyMs={4000} />}
      <RunsList runs={runs} showWorkflow />
    </>
  );
}

export default function RunsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="mt-1 text-sm text-muted">Every run in this workspace, newest first. Runs that need approval say so.</p>
      </div>
      <Suspense fallback={<p className="text-sm text-muted">Loading runs…</p>}>
        <AllRuns />
      </Suspense>
    </div>
  );
}
