"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, Approval, Project } from "@/lib/api";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);

  useEffect(() => {
    api<Project[]>("/projects").then(setProjects).catch(() => {});
    api<Approval[]>("/approvals?status_filter=pending").then(setApprovals).catch(() => {});
  }, []);

  return (
    <AppShell>
      <h1 className="text-lg font-semibold text-neutral-200 mb-6">Command Center</h1>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard label="Projects" value={projects.length} />
        <StatCard label="Pending Approvals" value={approvals.length} accent={approvals.length > 0} />
        <StatCard label="Active Agents" value={0} note="Security / Infra agents land in Phase 2" />
      </div>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-neutral-400">Recent Projects</h2>
        <Link href="/projects" className="text-xs text-emerald-400 hover:underline">
          View all →
        </Link>
      </div>
      <div className="flex flex-col gap-2">
        {projects.slice(0, 5).map((p) => (
          <Link
            key={p.id}
            href={`/projects/${p.id}`}
            className="block bg-base-near border border-base-border rounded px-4 py-3 hover:border-accent-emeraldBright transition-colors"
          >
            <div className="text-sm text-neutral-200">{p.name}</div>
            <div className="text-xs text-neutral-500 truncate">{p.idea}</div>
          </Link>
        ))}
        {projects.length === 0 && (
          <div className="text-sm text-neutral-600">
            No projects yet.{" "}
            <Link href="/projects" className="text-emerald-400 hover:underline">
              Create one
            </Link>
            .
          </div>
        )}
      </div>
    </AppShell>
  );
}

function StatCard({ label, value, note, accent }: { label: string; value: number; note?: string; accent?: boolean }) {
  return (
    <div className="bg-base-near border border-base-border rounded-lg p-4">
      <div className="text-xs text-neutral-500 mb-1">{label}</div>
      <div className={`text-2xl font-semibold ${accent ? "text-status-warning" : "text-neutral-200"}`}>{value}</div>
      {note && <div className="text-[10px] text-neutral-600 mt-1">{note}</div>}
    </div>
  );
}
