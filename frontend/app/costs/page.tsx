"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api, CostBucket, CostSummary } from "@/lib/api";

export default function CostsPage() {
  const [summary, setSummary] = useState<CostSummary | null>(null);

  useEffect(() => {
    api<CostSummary>("/costs").then(setSummary).catch(() => {});
  }, []);

  if (!summary) {
    return (
      <AppShell>
        <div className="text-neutral-500 text-sm">Loading…</div>
      </AppShell>
    );
  }

  const cacheRate =
    summary.total_input_tokens > 0
      ? (summary.total_cached_tokens / summary.total_input_tokens) * 100
      : 0;

  return (
    <AppShell>
      <h1 className="text-lg font-semibold text-neutral-200 mb-1">Costs</h1>
      <p className="text-sm text-neutral-500 mb-6">
        What the provider actually billed, falling back to our estimate only where it reported none.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Stat label="Total spend" value={`$${summary.total_cost_usd.toFixed(4)}`} accent />
        <Stat label="Requests" value={summary.total_requests.toLocaleString()} />
        <Stat label="Input tokens" value={summary.total_input_tokens.toLocaleString()} />
        <Stat label="Output tokens" value={summary.total_output_tokens.toLocaleString()} />
      </div>

      {summary.total_cached_tokens > 0 && (
        <p className="text-xs text-neutral-500 -mt-4 mb-8 tabular-nums">
          {summary.total_cached_tokens.toLocaleString()} cached input tokens ({cacheRate.toFixed(1)}% of input)
        </p>
      )}

      <Breakdown title="By role" note="Who is spending it" buckets={summary.by_role} total={summary.total_cost_usd} />
      <Breakdown title="By model" note="What it is being spent on" buckets={summary.by_model} total={summary.total_cost_usd} />
      <Breakdown title="By project" buckets={summary.by_project} total={summary.total_cost_usd} />
    </AppShell>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-base-near border border-base-border rounded-lg p-4">
      <div className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${accent ? "text-emerald-400" : "text-neutral-200"}`}>
        {value}
      </div>
    </div>
  );
}

function Breakdown({
  title,
  note,
  buckets,
  total,
}: {
  title: string;
  note?: string;
  buckets: CostBucket[];
  total: number;
}) {
  if (buckets.length === 0) return null;
  const max = Math.max(...buckets.map((b) => b.cost_usd), 0.000001);

  return (
    <section className="mb-8">
      <div className="flex items-baseline gap-3 mb-3">
        <h2 className="text-sm font-medium text-neutral-300">{title}</h2>
        {note && <span className="text-xs text-neutral-600">{note}</span>}
      </div>
      <div className="bg-base-near border border-base-border rounded-lg overflow-hidden">
        {buckets.map((b) => (
          <div key={b.key} className="px-4 py-2.5 border-b border-base-border last:border-b-0">
            <div className="flex items-center justify-between gap-4 mb-1.5">
              <span className="text-xs font-mono text-neutral-300 truncate">{b.key}</span>
              <span className="text-xs text-neutral-200 tabular-nums shrink-0">${b.cost_usd.toFixed(4)}</span>
            </div>
            <div className="h-1 bg-base-dark rounded-full overflow-hidden mb-1.5">
              <div
                className="h-full bg-accent-emeraldBright/70 rounded-full"
                style={{ width: `${Math.max((b.cost_usd / max) * 100, 1)}%` }}
              />
            </div>
            <div className="flex gap-4 text-[10px] text-neutral-600 tabular-nums">
              <span>{b.requests} req</span>
              <span>{b.input_tokens.toLocaleString()} in</span>
              <span>{b.output_tokens.toLocaleString()} out</span>
              {total > 0 && <span>{((b.cost_usd / total) * 100).toFixed(1)}%</span>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
