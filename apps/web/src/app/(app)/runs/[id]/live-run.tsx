"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { RunStatusBadge } from "@/components/run-status";
import { ACTION_LABEL } from "@/lib/steps";
import { FINISHED, type RunDetail, type RunStatus, type RunStep, type WorkflowSpec } from "@/lib/types";

import { cancelRun, decideCheckpoint } from "../../actions";

interface Checkpoint {
  step_id: string;
  reason: string;
  screenshot_ref: string;
  heal?: string | null;
}

type LiveEvent =
  | { type: "snapshot"; run: RunDetail }
  | { type: "step"; step_id: string; status: RunStep["status"]; error?: string; rung?: string; screenshot_ref?: string }
  | { type: "frame"; step_id: string; jpeg_b64: string }
  | ({ type: "checkpoint"; intent: string } & Checkpoint)
  | { type: "heal"; step_id: string; rung: string; score: number; explanation: string }
  | { type: "approved"; step_id: string }
  | { type: "done"; status: RunStatus };

const STEP_ICON: Record<string, string> = {
  running: "◌",
  ok: "✓",
  healed: "✓",
  failed: "✕",
  skipped: "–",
  awaiting_approval: "⏸",
};

interface StepState {
  status: RunStep["status"];
  error?: string;
  rung?: string;
  screenshot_ref?: string;
  heal?: string;
}

function toStates(steps: RunStep[]): Record<string, StepState> {
  return Object.fromEntries(
    steps.map((s) => [s.step_id, { status: s.status, error: s.error, rung: s.rung, screenshot_ref: s.screenshot_ref }]),
  );
}

function screenshot(runId: string, name: string): string {
  return `/bff/runs/${encodeURIComponent(runId)}/screenshots/${encodeURIComponent(name)}`;
}

export function LiveRun({ initial, spec }: { initial: RunDetail; spec: WorkflowSpec }) {
  const router = useRouter();
  const [status, setStatus] = useState<RunStatus>(initial.status);
  const [steps, setSteps] = useState<Record<string, StepState>>(() => toStates(initial.steps));
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState(initial.current_step_id);
  const [frame, setFrame] = useState<string | null>(null);
  const [checkpoint, setCheckpoint] = useState<Checkpoint | null>(() => {
    if (initial.status !== "awaiting_approval") return null;
    const step = initial.steps.find((s) => s.step_id === initial.current_step_id);
    const specStep = spec.steps.find((s) => s.id === initial.current_step_id);
    return { step_id: initial.current_step_id, reason: specStep?.checkpoint?.reason ?? "", screenshot_ref: step?.screenshot_ref ?? "" };
  });
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const finished = FINISHED.includes(status);

  useEffect(() => {
    if (FINISHED.includes(initial.status)) return;
    const source = new EventSource(`/bff/runs/${encodeURIComponent(initial.id)}/events`);
    const handle = (raw: MessageEvent<string>) => {
      const event = JSON.parse(raw.data) as LiveEvent;
      switch (event.type) {
        case "snapshot":
          setStatus(event.run.status);
          setCurrent(event.run.current_step_id);
          setSteps(toStates(event.run.steps));
          break;
        case "step":
          setCurrent(event.step_id);
          setSteps((prev) => ({
            ...prev,
            [event.step_id]: {
              ...prev[event.step_id],
              status: event.status,
              error: event.error,
              rung: event.rung,
              screenshot_ref: event.screenshot_ref,
            },
          }));
          if (event.status === "running") setStatus((s) => (s === "queued" ? "running" : s));
          break;
        case "heal":
          setSteps((prev) => ({
            ...prev,
            [event.step_id]: { ...(prev[event.step_id] ?? { status: "running" }), rung: event.rung, heal: event.explanation },
          }));
          break;
        case "frame":
          setFrame(event.jpeg_b64);
          break;
        case "checkpoint":
          setStatus("awaiting_approval");
          setCheckpoint({ step_id: event.step_id, reason: event.reason, screenshot_ref: event.screenshot_ref, heal: event.heal });
          setSteps((prev) => ({ ...prev, [event.step_id]: { status: "awaiting_approval" } }));
          break;
        case "approved":
          setCheckpoint(null);
          setStatus("running");
          break;
        case "done":
          setStatus(event.status);
          setCheckpoint(null);
          source.close();
          router.refresh(); // final outputs and errors come from the server render
          break;
      }
    };
    for (const type of ["snapshot", "step", "frame", "checkpoint", "heal", "approved", "done"]) {
      source.addEventListener(type, handle as EventListener);
    }
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false); // EventSource reconnects by itself
    return () => source.close();
  }, [initial.id, initial.status, router]);

  const decide = (decision: "approve" | "reject") =>
    start(async () => {
      if (!checkpoint) return;
      setError(null);
      const result = await decideCheckpoint(initial.id, checkpoint.step_id, decision);
      if (!result.ok) setError(result.message ?? "Couldn't send the decision.");
      else if (decision === "reject") setCheckpoint(null);
    });

  const cancel = () =>
    start(async () => {
      if (!window.confirm("Stop this run? Steps already done stay done.")) return;
      const result = await cancelRun(initial.id);
      if (!result.ok) setError(result.message ?? "Couldn't cancel.");
    });

  const checkpointStep = checkpoint ? spec.steps.find((s) => s.id === checkpoint.step_id) : null;
  // A picked step shows its after-action screenshot; a finished run opens on the last one.
  const lastShot = [...spec.steps].reverse().find((s) => steps[s.id]?.screenshot_ref)?.id ?? null;
  const shownStep = selected ?? (finished || !frame ? lastShot : null);
  const shownRef = shownStep ? steps[shownStep]?.screenshot_ref : undefined;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <RunStatusBadge status={status} />
        {!finished && (
          <span className="text-xs text-muted">{connected ? "● Live" : "Connecting…"}</span>
        )}
        {!finished && (
          <button type="button" onClick={cancel} disabled={pending} className="ml-auto rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas">
            Cancel run
          </button>
        )}
      </div>
      {error && <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

      {checkpoint && (
        <section className="space-y-3 rounded-lg border-2 border-warn bg-warn-soft p-4">
          <div>
            <p className="font-semibold text-warn">Approval needed: {checkpointStep?.intent ?? checkpoint.step_id}</p>
            <p className="text-sm">{checkpoint.reason}</p>
            <p className="mt-1 text-xs text-muted">The highlighted element is what will be clicked if you approve.</p>
            {checkpoint.heal && (
              <p className="mt-2 rounded-md bg-surface px-3 py-2 text-sm">
                <b>The page changed:</b> {checkpoint.heal} Check that the highlighted element is the right one.
              </p>
            )}
          </div>
          {checkpoint.screenshot_ref && (
            // eslint-disable-next-line @next/next/no-img-element -- short-lived storage links
            <img src={screenshot(initial.id, checkpoint.screenshot_ref)} alt="Page waiting for approval" className="max-h-[420px] rounded-md border border-line" />
          )}
          <div className="flex gap-2">
            <button type="button" disabled={pending} onClick={() => decide("approve")} className="rounded-md bg-ok px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
              Approve and continue
            </button>
            <button type="button" disabled={pending} onClick={() => decide("reject")} className="rounded-md border border-danger px-4 py-2 text-sm font-semibold text-danger disabled:opacity-60">
              Reject (stop the run)
            </button>
          </div>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          {shownRef && (selected || finished) ? (
            <figure>
              {/* eslint-disable-next-line @next/next/no-img-element -- short-lived storage links */}
              <img src={screenshot(initial.id, shownRef)} alt={`After step ${shownStep}`} className="w-full" />
              <figcaption className="border-t border-line px-3 py-2 text-xs text-muted">
                After: {spec.steps.find((s) => s.id === shownStep)?.intent}
                {selected && !finished && (
                  <button type="button" onClick={() => setSelected(null)} className="ml-2 text-accent hover:underline">
                    Back to live
                  </button>
                )}
              </figcaption>
            </figure>
          ) : frame ? (
            // eslint-disable-next-line @next/next/no-img-element -- live JPEG frames from the runner
            <img src={`data:image/jpeg;base64,${frame}`} alt="What the runner sees" className="w-full" />
          ) : (
            <div className="flex aspect-[16/10] items-center justify-center text-sm text-muted">
              {finished ? "No screenshots were taken." : "Waiting for the browser…"}
            </div>
          )}
        </div>
        <ol className="space-y-1.5">
          {spec.steps.map((step, n) => {
            const state = steps[step.id];
            const isCurrent = !finished && step.id === current;
            return (
              <li
                key={step.id}
                onClick={() => state?.screenshot_ref && setSelected(step.id)}
                className={`rounded-md border px-3 py-2 text-sm ${isCurrent ? "border-accent bg-accent/5" : "border-line bg-surface"} ${state?.status === "failed" ? "border-danger" : ""} ${step.id === shownStep && (selected || finished) ? "ring-2 ring-accent/40" : ""} ${state?.screenshot_ref ? "cursor-pointer hover:border-accent/60" : ""}`}
              >
                <div className="flex items-start gap-2">
                  <span className={`w-4 shrink-0 text-center ${state?.status === "failed" ? "text-danger" : state?.status === "ok" ? "text-ok" : "text-muted"}`}>
                    {state ? STEP_ICON[state.status] : n + 1}
                  </span>
                  <div className="min-w-0">
                    <div>
                      {step.intent}
                      {state?.rung === "L1" && <span className="ml-1 text-xs text-warn">(fallback locator)</span>}
                      {(state?.rung === "L2" || state?.rung === "L3") && (
                        <span className="ml-1 rounded bg-warn-soft px-1 text-xs text-warn">self-healed</span>
                      )}
                    </div>
                    <div className="text-xs text-muted">{ACTION_LABEL[step.action]}</div>
                    {state?.heal && <div className="mt-1 text-xs text-warn">{state.heal}</div>}
                    {state?.error && <div className="mt-1 text-xs text-danger">{state.error}</div>}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
