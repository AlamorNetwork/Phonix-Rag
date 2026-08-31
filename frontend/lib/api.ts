const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
export const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("phoenix_token");
}

export function setToken(token: string) {
  window.localStorage.setItem("phoenix_token", token);
}

export function clearToken() {
  window.localStorage.removeItem("phoenix_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}/api${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* no json body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export type Project = {
  id: string;
  name: string;
  idea: string;
  status: string;
  created_at: string;
};

export type AgentRun = {
  id: string;
  agent_id: string;
  project_id: string;
  status: string;
  input_message: string;
  output_message: string | null;
  created_at: string;
};

export type Approval = {
  id: string;
  tool_execution_id: string;
  agent_run_id: string;
  risk_level: string;
  reason: string;
  status: string;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
};

export type ModelInfo = {
  id: string;
  provider_id: string;
  model_id: string;
  input_price_per_1m: number;
  output_price_per_1m: number;
  context_window: number;
  enabled: boolean;
};

export type AgentInfo = {
  id: string;
  project_id: string;
  role: string;
  allowed_tools: string[];
  allowed_models: string[];
  selected_model_id: string | null;
  budget_usd: number;
  max_iterations: number;
};

export type Task = {
  id: string;
  project_id: string;
  order_index: number;
  title: string;
  description: string;
  assigned_role: string;
  status: string;
  attempts: number;
  estimated_cost_usd: number | null;
  agent_run_id: string | null;
  review_notes: string | null;
  created_at: string;
};

export type Plan = {
  project_id: string;
  project_status: string;
  tasks: Task[];
  estimated_total_usd: number | null;
};

export type ForgeEvent = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  agent_run_id: string | null;
  created_at: string;
};

export type CostBucket = {
  key: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cost_usd: number;
};

export type CostSummary = {
  total_cost_usd: number;
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cached_tokens: number;
  by_model: CostBucket[];
  by_role: CostBucket[];
  by_project: CostBucket[];
};
