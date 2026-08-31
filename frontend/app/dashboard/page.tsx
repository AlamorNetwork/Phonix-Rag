"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import {
  Chip,
  Metric,
  Panel,
  ROLE_DOT,
  ROLE_HUE,
  RISK_HUE,
  STATE_HUE,
  Sparkline,
  TaskBar,
  TimeAgo,
} from "@/components/ui";
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

type SeriesPoint = { bucket: string; cost_usd: number; requests: number };
type RoleLoad = { role: string; model_id: string | null; runs_active: number; cost_usd: number; requests: number };

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
  cost_series: SeriesPoint[];
  role_load: RoleLoad[];
};

const REFRESH_MS = 5000;
const ROLE_ORDER = ["manager", "architect", "coder", "reviewer"];

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api<Dashboard>("/dashboard"));
    } catch {
      /* keep the last good snapshot rather than blanking the console */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await load();
      if (!cancelled) timer = setTimeout(tick, REFRESH_MS);
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load]);

  async function decide(id: string, action: "approve" | "deny") {
    setDeciding(id);
    try {
      await api(`/approvals/${id}/${action}`, { method: "POST", body: "{}" });
      await load();
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
  const working = data.active_runs.length;
  const costs = data.cost_series.map((p) => p.cost_usd);
  const reqs = data.cost_series.map((p) => p.requests);
  const byRole = new Map(data.role_load.map((r) => [r.role, r]));

  return (
    <AppShell title="Command Center" subtitle="What needs you · what is running · what it costs">
      {/* Status band: the state of the whole system in one line, before any detail. */}
      <div
        className={`relative overflow-hidden rounded-xl border bg-base-near bg-panel-sheen shadow-panel px-5 py-4 mb-5 ${
          waiting > 0
            ? "border-status-warning/40"
            : working > 0
              ? "border-accent-emeraldBright/30 working-sweep"
              : "border-base-border"
        }`}
      >
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <span
              className={`w-2 h-2 rounded-full ${
                waiting > 0 ? "bg-status-warning" : working > 0 ? "bg-accent-emeraldBright" : "bg-neutral-700"
              } ${waiting > 0 || working > 0 ? "live-dot" : ""}`}
            />
            <span className="text-[15px] font-semibold tracking-tight text-neutral-50">
              {waiting > 0
                ? `${waiting} decision${waiting === 1 ? "" : "s"} waiting on you`
                : working > 0
                  ? `${working} agent${working === 1 ? "" : "s"} working`
                  : "Idle"}
            </span>
          </div>

          <span className="flex-1" />

          {/* The team, always visible: who exists, who is busy right now. */}
          <div className="flex items-center gap-1">
            {ROLE_ORDER.map((role) => {
              const load = byRole.get(role);
              const active = (load?.runs_active ?? 0) > 0;
              return (
                <div
                  key={role}
                  title={`${role}${load?.model_id ? ` · ${load.model_id}` : ""}${
                    active ? " · working" : ""
                  }`}
                  className={`flex items-center gap-1.5 rounded-md border px-2 py-1 transition-colors ${
                    active ? ROLE_HUE[role] : "border-base-border text-neutral-600"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${active ? ROLE_DOT[role] : "bg-neutral-700"} ${
                      active ? "live-dot" : ""
                    }`}
                  />
                  <span className="text-2xs capitalize">{role}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {waiting > 0 && (
        <Panel
          title="Waiting on you"
          note="Agents are paused until you decide"
          accent="warning"
          className="mb-5"
        >
          <div className="divide-y divide-base-border/70">
            {data.pending_approvals.map((a) => (
              <div key={a.id} className="px-4 py-3 flex items-center gap-3 flex-wrap">
                <Chip label={a.risk_level} tone={RISK_HUE[a.risk_level]} />
                <div className="flex-1 min-w-[16rem]">
                  <div className="text-[13px] text-neutral-200">{a.reason}</div>
                  <div className="text-2xs text-neutral-500 mt-0.5 flex gap-2">
                    {a.project_name && (
                      <Link href={`/projects/${a.project_id}`} className="hover:text-neutral-300">
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
                    className="bg-accent-emerald hover:bg-accent-emeraldBright hover:text-base-void text-white text-2xs font-semibold rounded-md px-3.5 py-1.5 transition-colors disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => decide(a.id, "deny")}
                    disabled={deciding === a.id}
                    className="border border-status-critical/40 text-status-critical hover:bg-status-critical/15 text-2xs rounded-md px-3.5 py-1.5 transition-colors disabled:opacity-50"
                  >
                    Deny
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <Metric
          label="Waiting on you"
          value={String(waiting)}
          urgent={waiting > 0}
          tone={waiting > 0 ? "text-status-warning" : "text-neutral-50"}
          sub={waiting > 0 ? "agents paused" : "nothing blocked"}
          href="/approvals"
        />
        <Metric
          label="Requests"
          value={String(reqs.reduce((a, b) => a + b, 0))}
          sub="last 24 hours"
          spark={reqs}
          sparkColor="#9d95ff"
        />
        <Metric
          label="Tasks"
          value={`${data.tasks_done}/${data.tasks_total}`}
          sub={data.tasks_blocked > 0 ? `${data.tasks_blocked} blocked` : "none blocked"}
          tone={data.tasks_blocked > 0 ? "text-status-critical" : "text-neutral-50"}
        />
        <Metric
          label="Spend"
          value={`$${data.cost_total_usd.toFixed(2)}`}
          sub={`$${data.cost_today_usd.toFixed(4)} today`}
          spark={costs}
          sparkColor="#22c99f"
          href="/costs"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 flex flex-col gap-5">
          {working > 0 && (
            <Panel title="Working now" accent="teal">
              <div className="divide-y divide-base-border/70">
                {data.active_runs.map((r) => (
                  <Link
                    key={r.id}
                    href={`/projects/${r.project_id}`}
                    className="px-4 py-2.5 flex items-center gap-3 hover:bg-base-graphite transition-colors"
                  >
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 live-dot ${ROLE_DOT[r.role]}`} />
                    <Chip label={r.role} tone={ROLE_HUE[r.role]} />
                    <span className="flex-1 min-w-0 text-[13px] text-neutral-300 truncate">
                      {r.input_message}
                    </span>
                    <span className="text-2xs text-neutral-600 font-mono truncate max-w-[11rem] hidden md:block">
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
              <Link href="/projects" className="text-2xs text-accent-emeraldBright hover:underline">
                All projects →
              </Link>
            }
          >
            <div className="divide-y divide-base-border/70">
              {data.projects.map((p) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="block px-4 py-3 hover:bg-base-graphite transition-colors group"
                >
                  <div className="flex items-center gap-2.5 mb-1">
                    <span className="text-[13px] font-medium text-neutral-100 truncate group-hover:text-white">
                      {p.name}
                    </span>
                    <Chip label={p.status} tone={STATE_HUE[p.status]} />
                    <span className="flex-1" />
                    {p.cost_usd > 0 && (
                      <span className="text-2xs text-neutral-500 num shrink-0">${p.cost_usd.toFixed(4)}</span>
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
                <div className="px-4 py-8 text-center">
                  <p className="text-sm text-neutral-400 mb-1">No projects yet</p>
                  <p className="text-2xs text-neutral-600 mb-3">
                    Describe an idea and the Manager will turn it into a costed plan.
                  </p>
                  <Link
                    href="/projects"
                    className="inline-block bg-accent-emerald hover:bg-accent-emeraldBright hover:text-base-void text-white text-2xs font-semibold rounded-md px-3.5 py-1.5 transition-colors"
                  >
                    New project
                  </Link>
                </div>
              )}
            </div>
          </Panel>
        </div>

        <div className="flex flex-col gap-5">
          {costs.length > 1 && (
            <Panel title="Spend" note="Per hour, last 24h">
              <div className="px-4 pt-3 pb-4">
                <Sparkline values={costs} stroke="#22c99f" height={64} />
                <div className="flex justify-between text-2xs text-neutral-600 num mt-2">
                  <span>24h ago</span>
                  <span>${Math.max(...costs).toFixed(4)} peak</span>
                  <span>now</span>
                </div>
              </div>
            </Panel>
          )}

          <Panel title="Activity" note="Newest first" className="self-start w-full">
            <div className="max-h-[30rem] overflow-y-auto divide-y divide-base-border/40">
              {data.recent_events.map((e) => (
                <div key={e.id} className="px-4 py-2 hover:bg-base-graphite/60 transition-colors">
                  <div className="flex items-baseline gap-2">
                    <span className={`text-2xs font-mono ${eventTone(e.event_type)}`}>{e.event_type}</span>
                    <span className="flex-1" />
                    <span className="text-2xs text-neutral-700">
                      <TimeAgo iso={e.created_at} />
                    </span>
                  </div>
                  <div className="text-2xs text-neutral-600 truncate mt-0.5">{summarise(e.payload)}</div>
                </div>
              ))}
              {data.recent_events.length === 0 && (
                <div className="px-4 py-6 text-2xs text-neutral-600">Nothing yet.</div>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}

function eventTone(type: string): string {
  if (type === "approval.required") return "text-status-warning";
  if (type.includes("denied") || type.includes("blocked") || type.includes("failed") || type.includes("rejected"))
    return "text-status-critical";
  if (type.includes("approved") || type.includes("completed")) return "text-status-success";
  if (type.startsWith("cost.") || type.startsWith("model.")) return "text-accent-irisBright";
  return "text-neutral-500";
}

/** Events carry very different payloads; show the field that says what happened rather than
 *  dumping raw JSON at the reader. */
function summarise(payload: Record<string, unknown>): string {
  for (const key of ["title", "reason", "tool", "detail", "model", "status", "agent_role"]) {
    const value = payload[key];
    if (typeof value === "string" && value) return value;
  }
  const json = JSON.stringify(payload);
  return json === "{}" ? "—" : json;
}
