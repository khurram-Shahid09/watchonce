import Link from "next/link";

import { ActionButton } from "@/components/client-bits";
import type { WorkflowDetail } from "@/lib/types";

import { activateVersion } from "../../actions";

const STATUS_STYLE: Record<string, string> = {
  active: "bg-ok/15 text-ok",
  draft: "bg-canvas text-muted",
  pending_heal: "bg-warn-soft text-warn",
  archived: "bg-canvas text-muted",
};

function author(createdBy: string): string {
  if (createdBy === "compiler") return "Compiled from the recording";
  if (createdBy === "healer") return "Self-healing";
  return "Edited in the dashboard";
}

export function VersionsView({ workflow, viewing, isOwner }: { workflow: WorkflowDetail; viewing: number; isOwner: boolean }) {
  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
      {[...workflow.versions]
        .sort((a, b) => b.version - a.version)
        .map((v) => (
          <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">Version {v.version}</span>
                <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[v.status] ?? ""}`}>
                  {v.status.replace("_", " ")}
                </span>
                {v.version === viewing && <span className="text-xs text-muted">(viewing)</span>}
              </div>
              <div className="text-sm text-muted">
                {author(v.created_by)} · {new Date(v.created_at).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" })}
                {v.change_note && ` · “${v.change_note}”`}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link href={`/workflows/${workflow.id}?v=${v.version}`} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas">
                View
              </Link>
              {isOwner && v.status !== "active" && (
                <ActionButton
                  action={activateVersion.bind(null, workflow.id, v.version)}
                  label="Make active"
                  confirm={`Make version ${v.version} the one that runs?`}
                />
              )}
            </div>
          </li>
        ))}
    </ul>
  );
}
