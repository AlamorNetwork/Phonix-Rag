"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentInfo, api, ApiError, ModelInfo } from "@/lib/api";

export function ModelPicker({ projectId, refreshKey }: { projectId: string; refreshKey?: number }) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [agent, setAgent] = useState<AgentInfo | null>(null);
  const [filter, setFilter] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  function loadAgent() {
    api<AgentInfo[]>(`/projects/${projectId}/agents`)
      .then((as) => setAgent(as.find((a) => a.role === "manager") ?? null))
      .catch(() => {});
  }

  useEffect(() => {
    api<ModelInfo[]>("/models").then(setModels).catch(() => {});
  }, []);

  // Re-read after a run: the agent may have switched its own model via model.switch.
  useEffect(loadAgent, [projectId, refreshKey]);

  const visible = useMemo(() => {
    const allowed = new Set(agent?.allowed_models ?? []);
    return models
      .filter((m) => m.enabled)
      .filter((m) => allowed.size === 0 || allowed.has(m.model_id))
      .filter((m) => m.model_id.toLowerCase().includes(filter.toLowerCase()))
      .sort((a, b) => a.model_id.localeCompare(b.model_id));
  }, [models, agent, filter]);

  async function select(modelId: string) {
    setSaving(true);
    setError(null);
    try {
      const updated = await api<AgentInfo>(`/projects/${projectId}/agents/manager/model`, {
        method: "PUT",
        body: JSON.stringify({ model_id: modelId }),
      });
      setAgent(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not switch model");
    } finally {
      setSaving(false);
    }
  }

  async function resync() {
    setSyncing(true);
    try {
      await api("/models/sync", { method: "POST", body: JSON.stringify({}) });
      setModels(await api<ModelInfo[]>("/models"));
    } catch {
      /* leave the existing list in place */
    } finally {
      setSyncing(false);
    }
  }

  const current = agent?.selected_model_id;

  return (
    <section className="bg-base-near border border-base-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-1">
        <div className="text-sm font-medium text-neutral-300">Model</div>
        <button
          onClick={resync}
          disabled={syncing}
          className="text-[10px] text-neutral-500 hover:text-neutral-300 border border-base-border rounded px-1.5 py-0.5 disabled:opacity-50"
        >
          {syncing ? "syncing…" : "resync"}
        </button>
      </div>
      <div className="text-xs text-emerald-400 mb-3 font-mono break-all">{current ?? "not set"}</div>

      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder={`Filter ${visible.length} models…`}
        className="w-full mb-2 bg-base-dark border border-base-border rounded px-2 py-1.5 text-xs focus:outline-none focus:border-accent-emeraldBright"
      />

      {error && <div className="text-status-critical text-[11px] mb-2">{error}</div>}

      <div className="max-h-64 overflow-y-auto flex flex-col gap-1">
        {visible.map((m) => {
          const active = m.model_id === current;
          return (
            <button
              key={m.id}
              onClick={() => select(m.model_id)}
              disabled={saving || active}
              className={`text-left px-2 py-1.5 rounded border text-[11px] transition-colors ${
                active
                  ? "border-accent-emeraldBright bg-accent-emerald/20 text-emerald-300"
                  : "border-base-border text-neutral-400 hover:border-neutral-600 hover:text-neutral-200"
              }`}
            >
              <div className="font-mono break-all">{m.model_id}</div>
              <div className="text-neutral-600 mt-0.5">
                ${m.input_price_per_1k.toFixed(5)} in / ${m.output_price_per_1k.toFixed(5)} out per 1k
                {m.context_window ? ` · ${(m.context_window / 1000).toFixed(0)}k ctx` : ""}
              </div>
            </button>
          );
        })}
        {visible.length === 0 && <div className="text-[11px] text-neutral-600">No models match.</div>}
      </div>

      <p className="text-[10px] text-neutral-600 mt-2">
        The Manager agent can also switch models itself via its <span className="font-mono">model.switch</span> tool —
        that needs your approval first.
      </p>
    </section>
  );
}
