import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { api, ApiError } from "@/lib/api";
import type { Me, Version, WorkflowDetail } from "@/lib/types";

import { EditView } from "./edit-view";
import { SopView } from "./sop-view";
import { StepsView } from "./steps-view";
import { VersionsView } from "./versions-view";

const TABS = [
  { id: "steps", label: "Steps" },
  { id: "sop", label: "SOP" },
  { id: "edit", label: "Edit" },
  { id: "versions", label: "Versions" },
] as const;
type Tab = (typeof TABS)[number]["id"];

async function load<T>(path: string): Promise<T> {
  try {
    return await api<T>(path);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}

export async function generateMetadata({ params }: PageProps<"/workflows/[id]">) {
  const { id } = await params;
  const workflow = await load<WorkflowDetail>(`/workflows/${encodeURIComponent(id)}`);
  return { title: workflow.name };
}

export default function WorkflowPage(props: PageProps<"/workflows/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading workflow…</p>}>
      <WorkflowContent {...props} />
    </Suspense>
  );
}

async function WorkflowContent({ params, searchParams }: PageProps<"/workflows/[id]">) {
  const { id } = await params;
  const query = await searchParams;
  const tab: Tab = TABS.some((t) => t.id === query.tab) ? (query.tab as Tab) : "steps";

  const [workflow, me] = await Promise.all([load<WorkflowDetail>(`/workflows/${encodeURIComponent(id)}`), api<Me>("/me")]);
  const active = workflow.active_version?.version ?? Math.max(...workflow.versions.map((v) => v.version));
  const requested = Number(query.v);
  const viewing = workflow.versions.some((v) => v.version === requested) ? requested : active;
  const version = await load<Version>(`/workflows/${encodeURIComponent(id)}/versions/${viewing}`);
  const isOwner = me.memberships[0]?.role === "owner";
  const href = (t: Tab) => `/workflows/${id}?tab=${t}${viewing !== active ? `&v=${viewing}` : ""}`;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/workflows" className="text-sm text-muted hover:text-ink">
          ← Workflows
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{workflow.name}</h1>
        {workflow.description && <p className="mt-1 max-w-3xl text-muted">{workflow.description}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <span>
            Version {viewing}
            {viewing === active ? " (active)" : ` · active is ${active}`}
          </span>
          <span>{version.spec.steps.length} steps</span>
          {version.compile_info.understand && <span>Compiled by {version.compile_info.understand.by}</span>}
        </div>
      </div>

      {viewing !== active && (
        <p className="rounded-md border border-line bg-surface px-4 py-2 text-sm">
          You are looking at version {viewing}. Runs use version {active}.{" "}
          <Link href={`/workflows/${id}?tab=${tab}`} className="text-accent hover:underline">
            Show the active version
          </Link>
        </p>
      )}

      <nav className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={href(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t.id ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink"}`}
          >
            {t.label}
            {t.id === "versions" && ` (${workflow.versions.length})`}
          </Link>
        ))}
      </nav>

      {tab === "steps" && <StepsView workflowId={id} version={version} />}
      {tab === "sop" && <SopView workflowId={id} version={version} />}
      {tab === "edit" && (
        <EditView key={version.id} workflowId={id} baseVersion={viewing} initial={version.spec} canActivate={isOwner} />
      )}
      {tab === "versions" && <VersionsView workflow={workflow} viewing={viewing} isOwner={isOwner} />}
    </div>
  );
}
