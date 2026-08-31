"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api, Approval } from "@/lib/api";

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [filter, setFilter] = useState<"pending" | "approved" | "denied" | "all">("pending");

  function refresh() {
    const query = filter === "all" ? "" : `?status_filter=${filter}`;
    api<Approval[]>(`/approvals${query}`).then(setApprovals).catch(() => {});
  }

  useEffect(refresh, [filter]);

  async function decide(id: string, decision: "approve" | "deny") {
    await api(`/approvals/${id}/${decision}`, { method: "POST", body: JSON.stringify({}) });
    refresh();
  }

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-neutral-200">Approvals</h1>
        <div className="flex gap-1">
          {(["pending", "approved", "denied", "all"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2.5 py-1 rounded border ${
                filter === f
                  ? "border-accent-emeraldBright text-emerald-400"
                  : "border-base-border text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {approvals.map((a) => (
          <div key={a.id} className="bg-base-near border border-base-border rounded-lg px-4 py-3">
            <div className="flex items-center justify-between">
              <span className={`text-xs font-medium risk-${a.risk_level}`}>{a.risk_level}</span>
              <span className="text-[10px] uppercase text-neutral-500">{a.status}</span>
            </div>
            <div className="text-sm text-neutral-300 mt-1">{a.reason}</div>
            <div className="text-[10px] text-neutral-600 mt-1">
              run {a.agent_run_id} · {new Date(a.created_at).toLocaleString()}
              {a.decided_by && ` · decided by ${a.decided_by}`}
            </div>
            {a.status === "pending" && (
              <div className="flex gap-2 mt-2">
                <button
                  onClick={() => decide(a.id, "approve")}
                  className="bg-status-success/20 text-status-success border border-status-success/40 rounded text-xs px-3 py-1 hover:bg-status-success/30"
                >
                  Approve
                </button>
                <button
                  onClick={() => decide(a.id, "deny")}
                  className="bg-status-critical/20 text-status-critical border border-status-critical/40 rounded text-xs px-3 py-1 hover:bg-status-critical/30"
                >
                  Deny
                </button>
              </div>
            )}
          </div>
        ))}
        {approvals.length === 0 && <div className="text-sm text-neutral-600">Nothing here.</div>}
      </div>
    </AppShell>
  );
}
