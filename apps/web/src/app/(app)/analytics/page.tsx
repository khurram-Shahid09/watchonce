import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";
import type { AnalyticsSummary } from "@/lib/types";

export const metadata: Metadata = { title: "Analytics" };

const RANGES = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
] as const;

function hours(value: number): string {
  if (value === 0) return "0 h";
  if (value < 1) return `${Math.round(value * 60)} min`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} h`;
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {note && <div className="mt-1 text-xs text-muted">{note}</div>}
    </div>
  );
}

/** Runs per day: one series, so the title names it and there is no legend. */
function DailyRuns({ daily }: { daily: AnalyticsSummary["daily"] }) {
  const max = Math.max(1, ...daily.map((d) => d.runs));
  const label = (d: string) =>
    new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return (
    <figure className="rounded-lg border border-line bg-surface p-4">
      <figcaption className="text-sm font-medium">Runs per day</figcaption>
      <div className="mt-4 flex h-32 items-end gap-0.5 border-b border-line" role="list">
        {daily.map((d) => (
          <div
            key={d.date}
            role="listitem"
            className="group relative flex h-full flex-1 items-end"
            aria-label={`${label(d.date)}: ${d.runs} runs, ${d.succeeded} succeeded`}
          >
            <div
              className="w-full rounded-t-[4px] bg-accent group-hover:opacity-80"
              style={{ height: d.runs ? `${Math.max(4, (d.runs / max) * 100)}%` : 0 }}
            />
            <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs shadow-sm group-hover:block">
              <div className="font-medium">{label(d.date)}</div>
              <div className="tabular-nums">
                {d.runs} runs · {d.succeeded} succeeded
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted">
        <span>{label(daily[0].date)}</span>
        <span>max {max} a day</span>
        <span>{label(daily[daily.length - 1].date)}</span>
      </div>
    </figure>
  );
}

async function Summary({ range }: { range: string }) {
  const data = await api<AnalyticsSummary>(`/analytics/summary?range=${range}`);
  const rate = data.success_rate === null ? "—" : `${Math.round(data.success_rate * 100)}%`;
  const missing = data.workflows_without_duration;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Hours saved"
          value={hours(data.hours_saved)}
          note={
            missing
              ? `${missing} workflow(s) without a manual time are not counted`
              : "Manual time × successful runs"
          }
        />
        <Tile label="Runs" value={data.runs.toLocaleString()} note={`${data.succeeded} succeeded`} />
        <Tile label="Success rate" value={rate} note="Of finished runs" />
        <Tile
          label="Heals"
          value={data.heals.toLocaleString()}
          note={`${data.heals_approved} approved · ${data.heals_pending} waiting · $${Number(data.llm_spend_usd).toFixed(2)} AI spend`}
        />
      </div>

      <DailyRuns daily={data.daily} />

      <section className="rounded-lg border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-3 text-sm font-medium">By workflow</h2>
        {data.workflows.length === 0 ? (
          <p className="px-4 py-6 text-sm text-muted">No runs in this period.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted">
                <tr>
                  <th className="px-4 py-2 font-normal">Workflow</th>
                  <th className="px-4 py-2 text-right font-normal">Runs</th>
                  <th className="px-4 py-2 text-right font-normal">Succeeded</th>
                  <th className="px-4 py-2 text-right font-normal">By hand</th>
                  <th className="px-4 py-2 text-right font-normal">Saved</th>
                </tr>
              </thead>
              <tbody>
                {data.workflows.map((w) => (
                  <tr key={w.workflow_id} className="border-t border-line">
                    <td className="px-4 py-2">
                      <Link href={`/workflows/${w.workflow_id}`} className="text-accent hover:underline">
                        {w.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{w.runs}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{w.succeeded}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {w.manual_duration_sec ? (
                        `${Math.round(w.manual_duration_sec / 60)} min`
                      ) : (
                        <Link href={`/workflows/${w.workflow_id}`} className="text-accent hover:underline">
                          Set
                        </Link>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{hours(w.hours_saved)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

async function Content({ searchParams }: PageProps<"/analytics">) {
  const query = await searchParams;
  const range = RANGES.some((r) => r.id === query.range) ? String(query.range) : "7d";
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
          <p className="mt-1 text-sm text-muted">What your automations did, and the time they saved.</p>
        </div>
        <nav className="flex gap-1 rounded-md border border-line bg-surface p-1 text-sm" aria-label="Time range">
          {RANGES.map((r) => (
            <Link
              key={r.id}
              href={`/analytics?range=${r.id}`}
              aria-current={r.id === range ? "page" : undefined}
              className={`rounded px-3 py-1 ${r.id === range ? "bg-canvas font-medium text-ink" : "text-muted hover:text-ink"}`}
            >
              {r.label}
            </Link>
          ))}
        </nav>
      </div>
      <Summary range={range} />
    </div>
  );
}

export default function AnalyticsPage(props: PageProps<"/analytics">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading analytics…</p>}>
      <Content {...props} />
    </Suspense>
  );
}
