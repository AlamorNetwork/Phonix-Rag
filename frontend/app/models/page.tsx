"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Chip, Panel, ROLE_HUE } from "@/components/ui";
import { api, ModelInfo } from "@/lib/api";

type RoleDefinition = {
  name: string;
  summary: string;
  default_model: string;
  budget_usd: number;
  max_iterations: number;
  timeout_seconds: number;
  allowed_tools: string[];
};

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [filter, setFilter] = useState("");
  const [syncing, setSyncing] = useState(false);

  function loadModels() {
    api<ModelInfo[]>("/models").then(setModels).catch(() => {});
  }

  useEffect(() => {
    loadModels();
    api<RoleDefinition[]>("/roles").then(setRoles).catch(() => {});
  }, []);

  async function resync() {
    setSyncing(true);
    try {
      await api("/models/sync", { method: "POST", body: "{}" });
      loadModels();
    } finally {
      setSyncing(false);
    }
  }

  const priced = useMemo(() => models.filter((m) => m.input_price_per_1m > 0), [models]);

  const visible = useMemo(
    () =>
      models
        .filter((m) => m.enabled && m.model_id.toLowerCase().includes(filter.toLowerCase()))
        .sort((a, b) => a.input_price_per_1m - b.input_price_per_1m),
    [models, filter],
  );

  const cheapest = priced.length ? Math.min(...priced.map((m) => m.input_price_per_1m)) : 0;
  const dearest = priced.length ? Math.max(...priced.map((m) => m.input_price_per_1m)) : 0;

  return (
    <AppShell
      title="Models"
      subtitle="The catalogue, and which model each role starts on"
      actions={
        <button
          onClick={resync}
          disabled={syncing}
          className="text-2xs text-neutral-400 hover:text-neutral-100 border border-base-border hover:border-base-borderStrong rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
        >
          {syncing ? "Syncing…" : "Resync catalogue"}
        </button>
      }
    >
      <Panel
        title="The team"
        note="What a new project is seeded with. Any project can override its own."
        className="mb-5"
      >
        <div className="divide-y divide-base-border/70">
          {roles.map((r) => (
            <div key={r.name} className="px-4 py-3 flex items-start gap-3 flex-wrap">
              <Chip label={r.name} tone={ROLE_HUE[r.name]} />
              <div className="flex-1 min-w-[14rem]">
                <div className="text-[13px] text-neutral-200">{r.summary}</div>
                <div className="text-2xs text-neutral-600 mt-1 flex flex-wrap gap-x-3 num">
                  <span>${r.budget_usd.toFixed(2)} per run</span>
                  <span>{r.max_iterations} iterations max</span>
                  <span>{r.allowed_tools.length} tools</span>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="font-mono text-2xs text-accent-emeraldBright">{r.default_model}</div>
                <PriceFor models={models} id={r.default_model} />
              </div>
            </div>
          ))}
          {roles.length === 0 && <div className="px-4 py-6 text-2xs text-neutral-600">Loading roles…</div>}
        </div>
      </Panel>

      <Panel
        title={`Catalogue · ${models.length} models`}
        note={
          priced.length
            ? `$${cheapest.toFixed(2)} to $${dearest.toFixed(2)} per 1M input tokens`
            : undefined
        }
        action={
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter…"
            className="bg-base-dark border border-base-border rounded-md px-2.5 py-1 text-2xs w-40 focus:outline-none focus:border-accent-emeraldBright"
          />
        }
      >
        <div className="max-h-[34rem] overflow-y-auto">
          <table className="w-full text-2xs">
            <thead className="sticky top-0 bg-base-near">
              <tr className="text-neutral-600 uppercase tracking-wider">
                <th className="text-left font-medium px-4 py-2">Model</th>
                <th className="text-right font-medium px-3 py-2">In /1M</th>
                <th className="text-right font-medium px-3 py-2">Out /1M</th>
                <th className="text-right font-medium px-4 py-2">Context</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-base-border/40">
              {visible.map((m) => (
                <tr key={m.id} className="hover:bg-base-graphite transition-colors">
                  <td className="px-4 py-1.5 font-mono text-neutral-300">{m.model_id}</td>
                  <td className="px-3 py-1.5 text-right num text-neutral-400">
                    ${m.input_price_per_1m.toFixed(2)}
                  </td>
                  <td className="px-3 py-1.5 text-right num text-neutral-400">
                    ${m.output_price_per_1m.toFixed(2)}
                  </td>
                  <td className="px-4 py-1.5 text-right num text-neutral-600">
                    {m.context_window ? `${(m.context_window / 1000).toFixed(0)}k` : "—"}
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-neutral-600">
                    No models match.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </AppShell>
  );
}

function PriceFor({ models, id }: { models: ModelInfo[]; id: string }) {
  const model = models.find((m) => m.model_id === id);
  if (!model) return <div className="text-2xs text-neutral-700 mt-0.5">not in catalogue</div>;
  return (
    <div className="text-2xs text-neutral-600 num mt-0.5">
      ${model.input_price_per_1m.toFixed(2)} / ${model.output_price_per_1m.toFixed(2)} per 1M
    </div>
  );
}
