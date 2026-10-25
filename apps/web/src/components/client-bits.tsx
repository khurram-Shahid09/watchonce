"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import type { SaveResult } from "@/app/(app)/actions";

/** Re-render the page every few seconds while something is still processing. */
export function AutoRefresh({ everyMs = 3000 }: { everyMs?: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = window.setInterval(() => router.refresh(), everyMs);
    return () => window.clearInterval(timer);
  }, [router, everyMs]);
  return null;
}

/** A button that runs a Server Function and shows its error, if any. */
export function ActionButton({
  action,
  label,
  pendingLabel,
  confirm,
  className = "rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas",
}: {
  action: () => Promise<SaveResult>;
  label: string;
  pendingLabel?: string;
  confirm?: string;
  className?: string;
}) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        disabled={pending}
        className={`${className} disabled:opacity-60`}
        onClick={() => {
          if (confirm && !window.confirm(confirm)) return;
          setError(null);
          start(async () => {
            const result = await action();
            if (!result.ok) setError(result.message ?? "Something went wrong.");
          });
        }}
      >
        {pending ? (pendingLabel ?? "Working…") : label}
      </button>
      {error && <span className="text-sm text-danger">{error}</span>}
    </span>
  );
}
