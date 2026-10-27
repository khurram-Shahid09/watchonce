"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { ACTION_LABEL } from "@/lib/steps";
import { AUTHORING_FINISHED, type AgentStep, type AuthoringSession, type AuthoringStatus } from "@/lib/types";

import { cancelAuthoring, decideAuthoring } from "../../actions";

type LiveEvent =
  | { type: "snapshot"; session: AuthoringSession }
  | ({ type: "agent_step" } & AgentStep)
  | { type: "frame"; jpeg_b64: string }
  | { type: "thinking"; message?: string }
  | { type: "checkpoint"; n: number; intent: string; reason: string }
  | { type: "approved"; n: number }
  | { type: "done"; status: AuthoringStatus; error?: string; workflow_id?: string; version?: number | null };

const ICON: Record<AgentStep["status"], string> = {
  running: "◌",
  ok: "✓",
  failed: "✕",
  awaiting_approval: "⏸",
  skipped: "–",
};

const STATUS_TEXT: Record<AuthoringStatus, string> = {
  queued: "Waiting for a browser…",
  running: "Working",
  awaiting_approval: "Waiting for you",
  succeeded: "Workflow saved",
  failed: "Stopped",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

function merge(steps: AgentStep[], step: AgentStep): AgentStep[] {
  const i = steps.findIndex((s) => s.n === step.n);
  if (i < 0) return [...steps, step];
  const next = [...steps];
  next[i] = { ...next[i], ...step };
  return next;
}

export function LiveAuthoring({ initial }: { initial: AuthoringSession }) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthoringStatus>(initial.status);
  const [steps, setSteps] = useState<AgentStep[]>(initial.steps);
  const [frame, setFrame] = useState<string | null>(null);
  const [thinking, setThinking] = useState<string | false>(false);
  const [question, setQuestion] = useState(initial.status === "awaiting_approval" ? initial.question : null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const finished = AUTHORING_FINISHED.includes(status);

  useEffect(() => {
    if (AUTHORING_FINISHED.includes(initial.status)) return;
    const source = new EventSource(`/bff/authoring/${encodeURIComponent(initial.id)}/events`);
    const handle = (raw: MessageEvent<string>) => {
      const event = JSON.parse(raw.data) as LiveEvent;
      switch (event.type) {
        case "snapshot":
          setStatus(event.session.status);
          setSteps(event.session.steps);
          break;
        case "agent_step": {
          // Status updates carry only what changed: keep the step's earlier fields.
          const step = Object.fromEntries(
            Object.entries(event).filter(([key, value]) => key !== "type" && value !== undefined),
          ) as unknown as AgentStep;
          setThinking(false);
          setStatus((s) => (s === "queued" ? "running" : s));
          setSteps((prev) => merge(prev, step));
          break;
        }
        case "thinking":
          setThinking(event.message ?? "The agent is looking at the page…");
          setStatus((s) => (s === "queued" ? "running" : s));
          break;
        case "frame":
          setFrame(event.jpeg_b64);
          break;
        case "checkpoint":
          setStatus("awaiting_approval");
          setThinking(false);
          setQuestion({ n: event.n, intent: event.intent, reason: event.reason });
          break;
        case "approved":
          setQuestion(null);
          setStatus("running");
          break;
        case "done":
          setStatus(event.status);
          setQuestion(null);
          setThinking(false);
          source.close();
          router.refresh();
          break;
      }
    };
    for (const type of ["snapshot", "agent_step", "frame", "thinking", "checkpoint", "approved", "done"]) {
      source.addEventListener(type, handle as EventListener);
    }
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    return () => source.close();
  }, [initial.id, initial.status, router]);

  const decide = (decision: "approve" | "reject") =>
    start(async () => {
      setError(null);
      const result = await decideAuthoring(initial.id, decision);
      if (!result.ok) setError(result.message ?? "Couldn't send the answer.");
      else setQuestion(null);
    });

  const cancel = () =>
    start(async () => {
      if (!window.confirm("Stop the agent? Nothing is saved.")) return;
      const result = await cancelAuthoring(initial.id);
      if (!result.ok) setError(result.message ?? "Couldn't cancel.");
    });

  const badge =
    status === "succeeded" ? "bg-ok/10 text-ok" : finished ? "bg-danger/10 text-danger" : status === "awaiting_approval" ? "bg-warn-soft text-warn" : "bg-accent/10 text-accent";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${badge}`}>{STATUS_TEXT[status]}</span>
        {!finished && <span className="text-xs text-muted">{connected ? "● Live" : "Connecting…"}</span>}
        {thinking && !finished && <span className="animate-pulse text-xs text-muted">{thinking}</span>}
        {!finished && (
          <button type="button" onClick={cancel} disabled={pending} className="ml-auto rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas">
            Stop
          </button>
        )}
      </div>
      {error && <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

      {question && (
        <section className="space-y-3 rounded-lg border-2 border-warn bg-warn-soft p-4">
          <div>
            <p className="font-semibold text-warn">Approval needed: {question.intent}</p>
            <p className="text-sm">{question.reason}</p>
            <p className="mt-1 text-xs text-muted">
              The highlighted element in the live view is what it will click. <b>Do it now</b> really does it on the site.{" "}
              <b>Keep without doing</b> saves the step (it will ask on every run) and finishes here.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={pending} onClick={() => decide("approve")} className="rounded-md bg-ok px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
              Do it now
            </button>
            <button type="button" disabled={pending} onClick={() => decide("reject")} className="rounded-md border border-warn px-4 py-2 text-sm font-semibold text-warn disabled:opacity-60">
              Keep without doing
            </button>
          </div>
        </section>
      )}

      {finished && <Outcome session={initial} status={status} />}

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          {frame ? (
            // eslint-disable-next-line @next/next/no-img-element -- live JPEG frames from the browser
            <img src={`data:image/jpeg;base64,${frame}`} alt="What the agent sees" className="w-full" />
          ) : (
            <div className="flex aspect-[16/10] items-center justify-center text-sm text-muted">
              {finished ? "The browser is closed." : "Opening the browser…"}
            </div>
          )}
        </div>
        <ol className="space-y-1.5">
          {steps.map((step) => (
            <li
              key={step.n}
              className={`rounded-md border px-3 py-2 text-sm ${step.status === "running" ? "border-accent bg-accent/5" : step.status === "failed" ? "border-danger/50" : step.status === "awaiting_approval" ? "border-warn" : "border-line bg-surface"}`}
            >
              <div className="flex items-start gap-2">
                <span className={`w-4 shrink-0 text-center ${step.status === "ok" ? "text-ok" : step.status === "failed" ? "text-danger" : "text-muted"}`}>
                  {ICON[step.status]}
                </span>
                <div className="min-w-0">
                  <div>{step.intent ?? "…"}</div>
                  {step.action && <div className="text-xs text-muted">{ACTION_LABEL[step.action as keyof typeof ACTION_LABEL] ?? step.action}</div>}
                  {step.value && <div className="mt-1 font-mono text-xs">Read: {step.value}</div>}
                  {step.status === "failed" && step.error && <div className="mt-1 text-xs text-danger">Didn&apos;t work: {step.error}. Trying another way…</div>}
                  {step.status === "skipped" && step.error && <div className="mt-1 text-xs text-warn">{step.error}</div>}
                </div>
              </div>
            </li>
          ))}
          {!finished && steps.length === 0 && <li className="text-sm text-muted">Starting…</li>}
        </ol>
      </div>
    </div>
  );
}

function Outcome({ session, status }: { session: AuthoringSession; status: AuthoringStatus }) {
  if (status === "succeeded" && session.workflow) {
    return (
      <section className="space-y-2 rounded-lg border border-ok/40 bg-ok/5 p-4">
        <p className="font-semibold">
          Saved: {session.workflow_name} {session.version_number ? `(version ${session.version_number})` : ""}
        </p>
        {session.error_message && <p className="text-sm text-muted">{session.error_message}</p>}
        <div className="flex flex-wrap gap-2 pt-1">
          <Link href={`/workflows/${session.workflow}?tab=run`} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white">
            Run it now
          </Link>
          <Link href={`/workflows/${session.workflow}?tab=steps`} className="rounded-md border border-line px-4 py-2 text-sm">
            Review the steps
          </Link>
        </div>
      </section>
    );
  }
  if (status === "succeeded") return null; // the page refreshes with the saved workflow
  return (
    <section className="space-y-2 rounded-lg border border-danger/40 bg-danger/5 p-4">
      <p className="font-semibold text-danger">{status === "cancelled" ? "Stopped." : "The agent couldn't finish."}</p>
      {session.error_message && <p className="text-sm">{session.error_message}</p>}
      <p className="text-sm text-muted">Add a hint to the instructions (what to click, what the page looks like) and try again.</p>
      <Link
        href={session.source_run ? `/runs/${session.source_run}` : "/workflows/new"}
        className="inline-block rounded-md border border-line bg-surface px-4 py-2 text-sm"
      >
        Try again
      </Link>
    </section>
  );
}
