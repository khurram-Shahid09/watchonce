import type { RunStatus } from "@/lib/types";

const LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  awaiting_approval: "Needs approval",
  succeeded: "Succeeded",
  failed: "Failed",
  rejected: "Rejected",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

const STYLE: Record<RunStatus, string> = {
  queued: "bg-canvas text-muted",
  running: "bg-accent/15 text-accent",
  awaiting_approval: "bg-warn-soft text-warn",
  succeeded: "bg-ok/15 text-ok",
  failed: "bg-danger/10 text-danger",
  rejected: "bg-danger/10 text-danger",
  cancelled: "bg-canvas text-muted",
  timed_out: "bg-danger/10 text-danger",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLE[status]}`}>{LABEL[status]}</span>;
}
