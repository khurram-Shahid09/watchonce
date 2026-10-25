"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import type { Batch, WorkflowSpec } from "@/lib/types";

import { createBatch } from "../../actions";

function csvCell(value: unknown): string {
  const text = value === undefined || value === null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** A template with the inputs as columns and the recorded examples as the first row. */
function templateCsv(spec: WorkflowSpec): string {
  const header = spec.inputs.map((i) => i.name).join(",");
  const example = spec.inputs.map((i) => csvCell(i.example)).join(",");
  return `${header}\n${example}\n`;
}

export function BatchView({ workflowId, spec, batches }: { workflowId: string; spec: WorkflowSpec; batches: Batch[] }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  // A file chosen before the page finished loading never fired our onChange: pick it up.
  useEffect(() => setFile((current) => current ?? input.current?.files?.[0] ?? null), []);
  const [message, setMessage] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, unknown> | null>(null);
  const [pending, start] = useTransition();
  const template = `data:text/csv;charset=utf-8,${encodeURIComponent(templateCsv(spec))}`;

  const submit = () =>
    start(async () => {
      if (!file) return;
      setMessage(null);
      setRowErrors(null);
      const form = new FormData();
      form.append("file", file);
      const result = await createBatch(workflowId, form);
      if (result.ok && result.batchId) {
        router.push(`/batches/${result.batchId}`);
        return;
      }
      setMessage(result.message ?? "Couldn't start the batch.");
      setRowErrors(result.rowErrors ?? null);
    });

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-line bg-surface p-5">
        <div>
          <h3 className="font-medium">Run once per row of a spreadsheet</h3>
          <p className="text-sm text-muted">
            One column per input ({spec.inputs.map((i) => i.name.replace(/_/g, " ")).join(", ") || "none"}). Rows run one
            after another; a failed row doesn&apos;t stop the others. At the first approval step you can approve it for the
            whole batch.
          </p>
        </div>
        <a href={template} download="batch-template.csv" className="inline-block text-sm text-accent hover:underline">
          Download a template CSV
        </a>
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={input}
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm file:mr-3 file:rounded-md file:border file:border-line file:bg-canvas file:px-3 file:py-1.5 file:text-sm"
          />
          <button
            type="button"
            disabled={!file || pending}
            onClick={submit}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {pending ? "Checking the file…" : "Start batch"}
          </button>
        </div>
        {message && (
          <div role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
            <p className="font-medium">{message}</p>
            {rowErrors && (
              <ul className="mt-1 list-disc pl-5">
                {Object.entries(rowErrors).map(([where, problem]) => (
                  <li key={where}>
                    {where}:{" "}
                    {typeof problem === "string"
                      ? problem
                      : Object.entries(problem as Record<string, string>)
                          .map(([field, text]) => `${field.replace(/_/g, " ")}: ${text}`)
                          .join("; ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {batches.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium text-muted">Earlier batches</h3>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {batches.map((b) => (
              <li key={b.id}>
                <Link href={`/batches/${b.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-canvas">
                  <span className="text-sm">
                    <b>{b.file_name || "Batch"}</b> · {b.total} rows · {new Date(b.created_at).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" })}
                  </span>
                  <span className="text-sm text-muted">
                    {b.status} · {b.succeeded} ok · {b.failed} failed
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
