import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { api, ApiError } from "@/lib/api";
import type { AuthoringSession } from "@/lib/types";

import { LiveAuthoring } from "./live-authoring";

export const metadata: Metadata = { title: "Building a workflow" };

export default function AuthoringPage(props: PageProps<"/authoring/[id]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <AuthoringContent {...props} />
    </Suspense>
  );
}

async function AuthoringContent({ params }: PageProps<"/authoring/[id]">) {
  const { id } = await params;
  let session: AuthoringSession;
  try {
    session = await api<AuthoringSession>(`/authoring/${encodeURIComponent(id)}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  return (
    <div className="space-y-6">
      <div>
        <Link href={session.source_run ? `/runs/${session.source_run}` : "/workflows"} className="text-sm text-muted hover:text-ink">
          ← {session.source_run ? "The failed run" : "Workflows"}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          {session.mode === "fix" ? "Fixing the workflow" : "Building a workflow"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          The agent does the task once in a real browser. Every step it takes is saved; later runs replay them without AI.
        </p>
      </div>
      <LiveAuthoring key={session.id} initial={session} />
      <details className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">Instructions</summary>
        <p className="mt-2 text-xs text-muted">Start: {session.start_url}</p>
        <pre className="mt-2 whitespace-pre-wrap font-mono text-xs leading-relaxed">{session.instructions}</pre>
      </details>
    </div>
  );
}
