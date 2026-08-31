"use client";

import { useEffect, useState } from "react";
import { api, ApiError, Plan, Task } from "@/lib/api";

const ROLE_TONE: Record<string, string> = {
  architect: "text-violet-300 border-violet-900/70 bg-violet-950/40",
  coder: "text-emerald-300 border-emerald-900/70 bg-emerald-950/40",
  reviewer: "text-sky-300 border-sky-900/70 bg-sky-950/40",
  manager: "text-amber-300 border-amber-900/70 bg-amber-950/40",
};

const STATUS_TONE: Record<string, string> = {
  pending: "text-neutral-500 border-base-border",
  running: "text-status-warning border-status-warning/40",
  in_review: "text-sky-400 border-sky-800",
  rejected: "text-status-critical border-status-critical/40",
  done: "text-status-success border-status-success/40",
  blocked: "text-status-critical border-status-critical/40",
};

export function PlanPanel({ projectId, refreshKey }: { projectId: string; refreshKey?: number }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api<Plan>(`/projects/${projectId}/plan`)
      .then(setPlan)
      .catch(() => {});
  }

  useEffect(load, [projectId, refreshKey]);

  async function decide(action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      setPlan(await api<Plan>(`/projects/${projectId}/plan/${action}`, { method: "POST", body: "{}" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Could not ${action} the plan`);
    } finally {
      setBusy(false);
    }
  }

  if (!plan) return null;

  const awaiting = plan.project_status === "plan_proposed";
  const done = plan.tasks.filter((t) => t.status === "done").length;

  return (
    <section className="bg-base-near border border-base-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-1">
        <div className="text-sm font-medium text-neutral-300">Plan</div>
        <span className="text-[10px] uppercase tracking-wider text-neutral-500 border border-base-border rounded px-1.5 py-0.5">
          {plan.project_status.replace(/_/g, " ")}
        </span>
      </div>

      {plan.tasks.length === 0 ? (
        <p className="text-xs text-neutral-600 mt-2">
          No plan yet. Run the Manager agent and ask it to plan the project.
        </p>
      ) : (
        <>
          <div className="flex items-center gap-3 text-[11px] text-neutral-500 mb-3 tabular-nums">
            <span>
              {plan.tasks.length} task{plan.tasks.length === 1 ? "" : "s"}
            </span>
            {done > 0 && <span className="text-status-success">{done} done</span>}
            {plan.estimated_total_usd != null && <span>est. ${plan.estimated_total_usd.toFixed(4)}</span>}
          </div>

          <ol className="flex flex-col gap-1.5">
            {plan.tasks.map((task) => (
              <TaskRow key={task.id} task={task} />
            ))}
          </ol>

          {awaiting && (
            <div className="mt-4 pt-3 border-t border-base-border">
              <p className="text-[11px] text-neutral-500 mb-2">
                Nothing runs until you approve. Approving starts the team on these tasks in order.
              </p>
              {error && <div className="text-status-critical text-[11px] mb-2">{error}</div>}
              <div className="flex gap-2">
                <button
                  onClick={() => decide("approve")}
                  disabled={busy}
                  className="flex-1 bg-accent-emerald hover:bg-accent-emeraldBright transition-colors text-xs font-medium rounded py-1.5 disabled:opacity-50"
                >
                  {busy ? "Working…" : "Approve plan"}
                </button>
                <button
                  onClick={() => decide("reject")}
                  disabled={busy}
                  className="flex-1 bg-status-critical/15 text-status-critical border border-status-critical/40 hover:bg-status-critical/25 transition-colors text-xs rounded py-1.5 disabled:opacity-50"
                >
                  Send back
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function TaskRow({ task }: { task: Task }) {
  const [open, setOpen] = useState(false);
  const roleTone = ROLE_TONE[task.assigned_role] ?? "text-neutral-400 border-base-border";
  const statusTone = STATUS_TONE[task.status] ?? "text-neutral-500 border-base-border";

  return (
    <li className="border border-base-border rounded bg-base-dark/40">
      <button
        onClick={() => setOpen(!open)}
        className="w-full text-left px-2.5 py-2 flex items-start gap-2 hover:bg-base-dark/70 transition-colors"
      >
        <span className="text-[10px] text-neutral-600 tabular-nums mt-0.5 w-4 shrink-0">
          {task.order_index + 1}
        </span>
        <span className={`text-[9.5px] uppercase tracking-wider border rounded px-1.5 py-0.5 shrink-0 mt-0.5 ${roleTone}`}>
          {task.assigned_role}
        </span>
        <span className="flex-1 min-w-0 text-xs text-neutral-200 leading-snug">{task.title}</span>
        <span className={`text-[9.5px] uppercase border rounded px-1.5 py-0.5 shrink-0 mt-0.5 ${statusTone}`}>
          {task.status.replace(/_/g, " ")}
        </span>
      </button>

      {open && (
        <div className="px-2.5 pb-2.5 pt-0 ml-6 text-[11px] text-neutral-400 space-y-2">
          {task.description && <p className="whitespace-pre-wrap leading-relaxed">{task.description}</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-neutral-600 tabular-nums">
            {task.estimated_cost_usd != null && <span>est. ${task.estimated_cost_usd.toFixed(4)}</span>}
            {task.attempts > 0 && <span>{task.attempts} attempt{task.attempts === 1 ? "" : "s"}</span>}
          </div>
          {task.review_notes && (
            <div className="border-l-2 border-status-critical/60 pl-2 text-status-critical/90 whitespace-pre-wrap">
              {task.review_notes}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
