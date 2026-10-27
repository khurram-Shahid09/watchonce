import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";
import type { Secret } from "@/lib/types";

import { InstructionsForm } from "./instructions-form";

export const metadata: Metadata = { title: "New workflow from instructions" };

export default function NewWorkflowPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link href="/workflows" className="text-sm text-muted hover:text-ink">
          ← Workflows
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">New workflow from instructions</h1>
        <p className="mt-1 text-sm text-muted">
          Write the task in plain words. An AI agent does it once in a real browser while you watch, and saves the
          steps as a workflow. Later runs replay those steps without AI.
        </p>
      </div>
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <FormWithLogins />
      </Suspense>
    </div>
  );
}

async function FormWithLogins() {
  const secrets = await api<Secret[]>("/secrets").catch(() => [] as Secret[]);
  return <InstructionsForm logins={secrets.map((s) => ({ name: s.name, fields: s.fields }))} />;
}
