"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ModelPicker } from "@/components/ModelPicker";
import { PlanPanel } from "@/components/PlanPanel";
import { api, Approval, AgentRun, ForgeEvent, getToken, Project, WS_BASE } from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [events, setEvents] = useState<ForgeEvent[]>([]);
  const [message, setMessage] = useState("");
  const [running, setRunning] = useState(false);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">("connecting");
  // Bumped when the agent may have changed its own model, so the picker re-reads it.
  const [modelRefreshKey, setModelRefreshKey] = useState(0);
  // Bumped when the plan may have changed: submitted, approved, or a task moved on.
  const [planRefreshKey, setPlanRefreshKey] = useState(0);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  function refreshRuns() {
    api<AgentRun[]>(`/projects/${projectId}/agents/runs`).then(setRuns).catch(() => {});
  }
  function refreshApprovals() {
    api<Approval[]>("/approvals?status_filter=pending").then(setApprovals).catch(() => {});
  }

  useEffect(() => {
    api<Project>(`/projects/${projectId}`).then(setProject).catch(() => {});
    refreshRuns();
    refreshApprovals();
  }, [projectId]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const ws = new WebSocket(`${WS_BASE}/ws/projects/${projectId}?token=${encodeURIComponent(token)}`);
    ws.onopen = () => setWsStatus("open");
    ws.onclose = () => setWsStatus("closed");
    ws.onmessage = (evt) => {
      const data: ForgeEvent = JSON.parse(evt.data);
      setEvents((prev) => [...prev.slice(-200), data]);
      if (data.type === "approval.required" || data.type.startsWith("approval.")) refreshApprovals();
      if (data.type === "agent.completed" || data.type === "agent.started") refreshRuns();
      if (data.type === "tool.completed" && data.payload?.tool === "model.switch") {
        setModelRefreshKey((k) => k + 1);
      }
      if (
        data.type.startsWith("plan.") ||
        data.type.startsWith("task.") ||
        (data.type === "tool.completed" && data.payload?.tool === "plan.submit")
      ) {
        setPlanRefreshKey((k) => k + 1);
      }
    };
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  const runIds = new Set(runs.map((r) => r.id));
  const relevantApprovals = approvals.filter((a) => runIds.has(a.agent_run_id));

  const sessionCost = events
    .filter((e) => e.type === "cost.recorded")
    .reduce((sum, e) => sum + (Number(e.payload.actual_cost ?? e.payload.estimated_cost ?? 0) || 0), 0);

  async function handleRun(e: React.FormEvent) {
    e.preventDefault();
    setRunning(true);
    try {
      await api(`/projects/${projectId}/agents/manager/run`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setMessage("");
      refreshRuns();
    } finally {
      setRunning(false);
    }
  }

  async function decide(id: string, decision: "approve" | "deny") {
    await api(`/approvals/${id}/${decision}`, { method: "POST", body: JSON.stringify({}) });
    refreshApprovals();
  }

  if (!project) {
    return (
      <AppShell>
        <div className="text-neutral-500 text-sm">Loading…</div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-neutral-200">{project.name}</h1>
        <p className="text-sm text-neutral-500 mt-1">{project.idea}</p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 flex flex-col gap-6">
          <section className="bg-base-near border border-base-border rounded-lg p-4">
            <div className="text-sm font-medium text-neutral-300 mb-3">Run Manager Agent</div>
            <form onSubmit={handleRun} className="flex gap-2">
              <input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                required
                placeholder="Tell the Manager agent what to do…"
                className="flex-1 bg-base-dark border border-base-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-emeraldBright"
              />
              <button
                type="submit"
                disabled={running}
                className="bg-accent-emerald hover:bg-accent-emeraldBright transition-colors text-sm font-medium rounded px-4 py-2 disabled:opacity-50"
              >
                {running ? "Starting…" : "Run"}
              </button>
            </form>
          </section>

          <section className="bg-base-near border border-base-border rounded-lg p-4 flex-1">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-medium text-neutral-300">Live Events</div>
              <span
                className={`text-[10px] uppercase px-1.5 py-0.5 rounded border ${
                  wsStatus === "open"
                    ? "border-status-success text-status-success"
                    : "border-base-border text-neutral-500"
                }`}
              >
                {wsStatus}
              </span>
            </div>
            <div className="h-96 overflow-y-auto font-mono text-xs flex flex-col gap-1 bg-base-black rounded p-3 border border-base-border">
              {events.length === 0 && <div className="text-neutral-600">No events yet — run the agent above.</div>}
              {events.map((e) => (
                <div key={e.id} className="text-neutral-400">
                  <span className="text-neutral-600">{new Date(e.created_at).toLocaleTimeString()}</span>{" "}
                  <span className="text-emerald-500">{e.type}</span>{" "}
                  <span className="text-neutral-500">{JSON.stringify(e.payload)}</span>
                </div>
              ))}
              <div ref={eventsEndRef} />
            </div>
          </section>

          <section className="bg-base-near border border-base-border rounded-lg p-4">
            <div className="text-sm font-medium text-neutral-300 mb-3">Agent Runs</div>
            <div className="flex flex-col gap-2">
              {runs.map((r) => (
                <div key={r.id} className="border border-base-border rounded px-3 py-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-neutral-400">{r.input_message}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  {r.output_message && <div className="text-xs text-neutral-500 mt-1">{r.output_message}</div>}
                </div>
              ))}
              {runs.length === 0 && <div className="text-xs text-neutral-600">No runs yet.</div>}
            </div>
          </section>
        </div>

        <div className="flex flex-col gap-6">
          <PlanPanel projectId={projectId} refreshKey={planRefreshKey} />

          <ModelPicker projectId={projectId} refreshKey={modelRefreshKey} />

          <section className="bg-base-near border border-base-border rounded-lg p-4">
            <div className="text-sm font-medium text-neutral-300 mb-1">Session Cost</div>
            <div className="text-2xl font-semibold text-neutral-200">${sessionCost.toFixed(4)}</div>
            <div className="text-[10px] text-neutral-600 mt-1">Live total from this browser session's events</div>
          </section>

          <section className="bg-base-near border border-base-border rounded-lg p-4">
            <div className="text-sm font-medium text-neutral-300 mb-3">Pending Approvals</div>
            <div className="flex flex-col gap-2">
              {relevantApprovals.map((a) => (
                <div key={a.id} className="border border-base-border rounded px-3 py-2">
                  <div className={`text-xs font-medium risk-${a.risk_level}`}>{a.risk_level}</div>
                  <div className="text-xs text-neutral-400 mt-0.5">{a.reason}</div>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => decide(a.id, "approve")}
                      className="flex-1 bg-status-success/20 text-status-success border border-status-success/40 rounded text-xs py-1 hover:bg-status-success/30"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => decide(a.id, "deny")}
                      className="flex-1 bg-status-critical/20 text-status-critical border border-status-critical/40 rounded text-xs py-1 hover:bg-status-critical/30"
                    >
                      Deny
                    </button>
                  </div>
                </div>
              ))}
              {relevantApprovals.length === 0 && (
                <div className="text-xs text-neutral-600">Nothing waiting on you right now.</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "text-status-success border-status-success/40"
      : status === "failed" || status === "blocked" || status === "timeout"
        ? "text-status-critical border-status-critical/40"
        : status === "running"
          ? "text-status-warning border-status-warning/40"
          : "text-neutral-500 border-base-border";
  return <span className={`text-[10px] uppercase border rounded px-1.5 py-0.5 ${color}`}>{status}</span>;
}
