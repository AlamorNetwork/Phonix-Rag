"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { api, ApiError, Project } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [idea, setIdea] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  function refresh() {
    api<Project[]>("/projects").then(setProjects).catch(() => {});
  }

  useEffect(refresh, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCreating(true);
    try {
      await api<Project>("/projects", { method: "POST", body: JSON.stringify({ name, idea }) });
      setName("");
      setIdea("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <AppShell>
      <h1 className="text-lg font-semibold text-neutral-200 mb-6">Projects</h1>

      <form onSubmit={handleCreate} className="bg-base-near border border-base-border rounded-lg p-4 mb-6">
        <div className="text-sm font-medium text-neutral-300 mb-3">New Project</div>
        <input
          placeholder="Project name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full mb-2 bg-base-dark border border-base-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-emeraldBright"
        />
        <textarea
          placeholder="Describe the idea…"
          required
          rows={3}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          className="w-full mb-3 bg-base-dark border border-base-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-emeraldBright"
        />
        {error && <div className="text-status-critical text-xs mb-2">{error}</div>}
        <button
          type="submit"
          disabled={creating}
          className="bg-accent-emerald hover:bg-accent-emeraldBright transition-colors text-sm font-medium rounded px-4 py-2 disabled:opacity-50"
        >
          {creating ? "Creating…" : "Create Project"}
        </button>
      </form>

      <div className="flex flex-col gap-2">
        {projects.map((p) => (
          <Link
            key={p.id}
            href={`/projects/${p.id}`}
            className="block bg-base-near border border-base-border rounded px-4 py-3 hover:border-accent-emeraldBright transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="text-sm text-neutral-200">{p.name}</div>
              <span className="text-[10px] uppercase text-neutral-500 border border-base-border rounded px-1.5 py-0.5">
                {p.status}
              </span>
            </div>
            <div className="text-xs text-neutral-500 truncate mt-1">{p.idea}</div>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
