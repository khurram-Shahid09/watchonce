"use client";

import { useState, useTransition } from "react";

import { setManualDuration } from "../../actions";

/** "Takes about N min by hand": the basis for hours saved on the analytics page. */
export function ManualTime({ workflowId, seconds }: { workflowId: string; seconds: number | null }) {
  const [editing, setEditing] = useState(false);
  const [minutes, setMinutes] = useState(seconds ? String(Math.round(seconds / 60)) : "");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  if (!editing) {
    return (
      <span>
        {seconds ? `Takes about ${Math.round(seconds / 60)} min by hand` : "Manual time not set"} ·{" "}
        <button type="button" className="text-accent hover:underline" onClick={() => setEditing(true)}>
          {seconds ? "Change" : "Set it"}
        </button>
      </span>
    );
  }
  return (
    <form
      className="inline-flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const value = minutes.trim() === "" ? null : Number(minutes);
        if (value !== null && (!Number.isFinite(value) || value < 0 || value > 24 * 60)) {
          setError("Enter minutes between 0 and 1440.");
          return;
        }
        setError(null);
        start(async () => {
          const result = await setManualDuration(workflowId, value === null ? null : Math.round(value * 60));
          if (result.ok) setEditing(false);
          else setError(result.message ?? "Couldn't save.");
        });
      }}
    >
      <label htmlFor="manual-minutes">Minutes by hand</label>
      <input
        id="manual-minutes"
        type="number"
        min={0}
        max={1440}
        step={1}
        value={minutes}
        onChange={(e) => setMinutes(e.target.value)}
        className="w-20 rounded-md border border-line bg-surface px-2 py-0.5 text-ink"
      />
      <button type="submit" disabled={pending} className="rounded-md border border-line px-2 py-0.5 hover:bg-canvas disabled:opacity-60">
        {pending ? "Saving…" : "Save"}
      </button>
      <button type="button" className="text-muted hover:text-ink" onClick={() => setEditing(false)}>
        Cancel
      </button>
      {error && <span className="text-danger">{error}</span>}
    </form>
  );
}
