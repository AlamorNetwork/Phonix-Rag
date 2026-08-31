"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

type StoredEvent = {
  id: string;
  project_id: string | null;
  agent_run_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

// Event families, coloured by what they mean rather than by string prefix alone: things a
// human must act on, things that cost money, and things that went wrong stand out.
function toneFor(type: string): string {
  if (type.startsWith("approval.required") || type === "plan.rejected") return "text-status-warning";
  if (type.endsWith(".denied") || type.includes("blocked") || type.includes("failed") || type.includes("rejected"))
    return "text-status-critical";
  if (type.endsWith(".approved") || type.endsWith(".completed") || type === "plan.approved")
    return "text-status-success";
  if (type.startsWith("cost.") || type.startsWith("model.")) return "text-sky-400";
  return "text-emerald-500";
}

export default function EventsPage() {
  const [events, setEvents] = useState<StoredEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<StoredEvent[]>("/events?limit=300")
      .then(setEvents)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(
    () =>
      events.filter(
        (e) =>
          !filter ||
          e.event_type.includes(filter.toLowerCase()) ||
          JSON.stringify(e.payload).toLowerCase().includes(filter.toLowerCase()),
      ),
    [events, filter],
  );

  const types = useMemo(() => {
    const counts = new Map<string, number>();
    events.forEach((e) => counts.set(e.event_type, (counts.get(e.event_type) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [events]);

  return (
    <AppShell>
      <h1 className="text-lg font-semibold text-neutral-200 mb-1">Events</h1>
      <p className="text-sm text-neutral-500 mb-5">
        Every action the system took, in order. Secrets are masked before anything is written here.
      </p>

      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter by type or payload…"
        className="w-full max-w-md mb-3 bg-base-dark border border-base-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-emeraldBright"
      />

      {types.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-5">
          {types.map(([type, count]) => (
            <button
              key={type}
              onClick={() => setFilter(filter === type ? "" : type)}
              className={`text-[10px] font-mono border rounded px-2 py-0.5 transition-colors ${
                filter === type
                  ? "border-accent-emeraldBright text-emerald-400"
                  : "border-base-border text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {type} <span className="text-neutral-600">{count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="bg-base-near border border-base-border rounded-lg overflow-hidden">
        {loading && <div className="px-4 py-3 text-xs text-neutral-600">Loading…</div>}
        {!loading && visible.length === 0 && (
          <div className="px-4 py-3 text-xs text-neutral-600">No events match.</div>
        )}
        {visible.map((e) => (
          <div key={e.id} className="px-4 py-2 border-b border-base-border last:border-b-0 font-mono text-[11px]">
            <div className="flex items-baseline gap-3">
              <span className="text-neutral-600 shrink-0 tabular-nums">
                {new Date(e.created_at).toLocaleTimeString()}
              </span>
              <span className={`shrink-0 ${toneFor(e.event_type)}`}>{e.event_type}</span>
              <span className="text-neutral-500 truncate">{JSON.stringify(e.payload)}</span>
            </div>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
