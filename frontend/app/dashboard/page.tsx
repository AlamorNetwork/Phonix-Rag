"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { Chip, Metric, Panel, ROLE_HUE, RISK_HUE, STATE_HUE, TaskBar, TimeAgo } from "@/components/ui";
import { api } from "@/lib/api";

type PendingApproval = {
  id: string;
  risk_level: string;
  reason: string;
  agent_run_id: string;
  project_id: string | null;
  project_name: string | null;
  created_at: string;
};

type ActiveRun = {
  id: string;
  project_id: string;
  project_name: string;
  role: string;
  model_id: string | null;
  status: string;
  input_message: string;
  started_at: string | null;
};

type ProjectCard = {
  id: string;
  name: string;
  idea: string;
  status: string;
  tasks_total: number;
  tasks_done: number;
  tasks_blocked: number;
  cost_usd: number;
  created_at: string;
};

type RecentEvent = {
  id: string;
  event_type: string;
  project_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

type Dashboard = {
  pending_approvals: PendingApproval[];
  active_runs: ActiveRun[];
  projects_total: number;
  projects_executing: number;
  tasks_total: number;
  tasks_done: number;
  tasks_blocked: number;
  cost_total_usd: number;
  cost_today_usd: number;
  tokens_in: number;
  tokens_out: number;
  projects: ProjectCard[];
  recent_events: RecentEvent[];
};

const REFRESH_MS = 5000;

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Dashboard>("/dashboard")
      .then(setData)
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    // Agents work while nobody is looking, so the console keeps itself current.
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  async function decide(id: string, action: "approve" | "deny") {
    setDeciding(id);
    try {
      await api(`/approvals/${id}/${action}`, { method: "POST", body: "{}" });
      load();
    } finally {
      setDeciding(null);
    }
  }

  if (!data) {
    return (
      <AppShell title="Command Center">
        <div className="text-neutral-600 text-sm">Loading…</div>
      </AppShell>
    );
  }

  const waiting = data.pending_approvals.length;
  const tokensTotal = data.tokens_in + data.tokens_out;

  return (
    <AppShell
      title="Command Center"
      subtitle="What needs you, what is running, what it costs"
      actions={
        <span className="flex items-center gap-1.5 text-2xs text-neutral-600">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-emeraldBright live-dot" />
          live
        </span>
      }
    >
      {/* Anything waiting on a human is the first thing on the page - it is the one thing
          that will not resolve itself. */}
      {waiting > 0 && (
        <Panel
          title={`${waiting} action${waiting === 1 ? "" : "s"} waiting on you`}
          note="Agents are paused until you decide"
          className="mb-6 border-status-warning/40"
        >
          <div className="divide-y divide-base-border">
            {data.pending_approvals.map((a) => (
              <div key={a.id} className="px-4 py-3 flex items-center gap-3 flex-wrap">
                <Chip label={a.risk_level} tone={RISK_HUE[a.risk_level]} />
                <div className="flex-1 min-w-[16rem]">
                  <div className="text-[13px] text-neutral-200">{a.reason}</div>
                  <div className="text-2xs text-neutral-600 mt-0.5 flex gap-2">
                    {a.project_name && (
                      <Link href={`/projects/${a.project_id}`} className="hover:text-neutral-400">
                        {a.project_name}
                      </Link>
                    )}
                    <TimeAgo iso={a.created_at} />
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => decide(a.id, "approve")}
                    disabled={deciding === a.id}
                    className="bg-accent-emerald hover:bg-accent-emeraldBright text-white text-2xs font-medium rounded px-3 py-1.5 transition-colors disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => decide(a.id, "deny")}
                    disabled={deciding === a.id}
                    className="border border-status-critical/40 text-status-critical hover:bg-status-critical/15 text-2xs rounded px-3 py-1.5 transition-colors disabled:opacity-50"
                  >
                    Deny
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <Metric
          label="Waiting on you"
          value={String(waiting)}
          tone={waiting > 0 ? "text-status-warning" : "text-neutral-100"}
          sub={waiting > 0 ? "agents are paused" : "nothing blocked"}
          href="/approvals"
        />
        <Metric
          label="Agents working"
          value={String(data.active_runs.length)}
          sub={`${data.projects_executing} project${data.projects_executing === 1 ? "" : "s"} executing`}
          tone={data.active_runs.length > 0 ? "text-accent-emeraldBright" : "text-neutral-100"}
        />
        <Metric
          label="Tasks done"
          value={`${data.tasks_done}/${data.tasks_total}`}
          sub={data.tasks_blocked > 0 ? `${data.tasks_blocked} blocked` : "none blocked"}
          tone={data.tasks_blocked > 0 ? "text-status-critical" : "text-neutral-100"}
        />
        <Metric
          label="Spend"
          value={`$${data.cost_total_usd.toFixed(2)}`}
          sub={`$${data.cost_today_usd.toFixed(4)} today · ${(tokensTotal / 1000).toFixed(0)}k tokens`}
          href="/costs"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 flex flex-col gap-6">
          {data.active_runs.length > 0 && (
            <Panel title="Working now">
              <div className="divide-y divide-base-border">
                {data.active_runs.map((r) => (
                  <Link
                    key={r.id}
                    href={`/projects/${r.project_id}`}
                    className="px-4 py-2.5 flex items-center gap-3 hover:bg-base-graphite transition-colors"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-emeraldBright live-dot shrink-0" />
                    <Chip label={r.role} tone={ROLE_HUE[r.role]} />
                    <span className="flex-1 min-w-0 text-[13px] text-neutral-300 truncate">
                      {r.input_message}
                    </span>
                    <span className="text-2xs text-neutral-600 font-mono truncate max-w-[12rem] hidden md:block">
                      {r.model_id}
                    </span>
                  </Link>
                ))}
              </div>
            </Panel>
          )}

          <Panel
            title="Projects"
            action={
              <Link href="/projects" className="text-2xs text-emerald-500 hover:text-emerald-400">
                All projects →
              </Link>
            }
          >
            <div className="divide-y divide-base-border">
              {data.projects.map((p) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="block px-4 py-3 hover:bg-base-graphite transition-colors"
                >
                  <div className="flex items-center gap-2.5 mb-1">
                    <span className="text-[13px] font-medium text-neutral-100 truncate">{p.name}</span>
                    <Chip label={p.status} tone={STATE_HUE[p.status]} />
                    <span className="flex-1" />
                    {p.cost_usd > 0 && (
                      <span className="text-2xs text-neutral-500 num shrink-0">
                        ${p.cost_usd.toFixed(4)}
                      </span>
                    )}
                  </div>
                  <p className="text-2xs text-neutral-600 line-clamp-1 mb-2">{p.idea}</p>
                  {p.tasks_total > 0 && (
                    <div className="flex items-center gap-2.5">
                      <TaskBar total={p.tasks_total} done={p.tasks_done} blocked={p.tasks_blocked} />
                      <span className="text-2xs text-neutral-600 num shrink-0">
                        {p.tasks_done}/{p.tasks_total}
                      </span>
                    </div>
                  )}
                </Link>
              ))}
              {data.projects.length === 0 && (
                <div className="px-4 py-6 text-center">
                  <p className="text-sm text-neutral-500 mb-2">No projects yet.</p>
                  <Link href="/projects" className="text-2xs text-emerald-500 hover:text-emerald-400">
                    Describe an idea to get started →
                  </Link>
                </div>
              )}
            </div>
          </Panel>
        </div>

        <Panel title="Activity" note="Everything the system just did" className="self-start">
          <div className="max-h-[36rem] overflow-y-auto divide-y divide-base-border/60">
            {data.recent_events.map((e) => (
              <div key={e.id} className="px-4 py-2">
                <div className="flex items-baseline gap-2">
                  <span className={`text-2xs font-mono ${eventTone(e.event_type)}`}>{e.event_type}</span>
                  <span className="flex-1" />
                  <span className="text-2xs text-neutral-700">
                    <TimeAgo iso={e.created_at} />
                  </span>
                </div>
                <div className="text-2xs text-neutral-600 font-mono truncate mt-0.5">
                  {summarise(e.payload)}
                </div>
              </div>
            ))}
            {data.recent_events.length === 0 && (
              <div className="px-4 py-6 text-2xs text-neutral-600">Nothing yet.</div>
            )}
          </div>
        </Panel>
      </div>
    </AppShell>
  );
}

function eventTone(type: string): string {
  if (type === "approval.required") return "text-status-warning";
  if (type.includes("denied") || type.includes("blocked") || type.includes("failed") || type.includes("rejected"))
    return "text-status-critical";
  if (type.includes("approved") || type.includes("completed")) return "text-status-success";
  if (type.startsWith("cost.") || type.startsWith("model.")) return "text-status-info";
  return "text-neutral-500";
}

/** Events carry very different payloads; show the field that actually says what happened
 *  rather than dumping raw JSON at the reader. */
function summarise(payload: Record<string, unknown>): string {
  for (const key of ["title", "reason", "tool", "detail", "model", "status", "agent_role"]) {
    const value = payload[key];
    if (typeof value === "string" && value) return value;
  }
  const json = JSON.stringify(payload);
  return json === "{}" ? "—" : json;
}
