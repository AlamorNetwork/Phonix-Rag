"use client";

import { useState } from "react";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.access_token);
      // A hard navigation, not router.replace: the client-side replace was landing the token
      // in storage and then not navigating at all, leaving you staring at the login form after
      // a successful sign-in. A full load is the right thing on an auth transition anyway -
      // it starts the app with clean state rather than whatever the login page left behind.
      window.location.assign("/dashboard");
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-black field">
      <form onSubmit={handleSubmit} className="w-full max-w-sm bg-base-near border border-base-border rounded-xl shadow-panel bg-panel-sheen p-8">
        <div className="flex items-center gap-2 mb-1"><span className="w-1.5 h-1.5 rounded-full bg-accent-emeraldBright live-dot" /><span className="text-neutral-50 font-semibold tracking-[0.14em] text-sm">PHOENIX FORGE</span></div>
        <div className="text-2xs text-neutral-500 mb-7 ml-3.5">AI Engineering & Infrastructure Command Center</div>

        <label className="block text-xs text-neutral-400 mb-1">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full mb-4 bg-base-dark border border-base-border rounded px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-accent-emeraldBright rounded-md"
        />

        <label className="block text-xs text-neutral-400 mb-1">Password</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-6 bg-base-dark border border-base-border rounded px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-accent-emeraldBright rounded-md"
        />

        {error && <div className="text-status-critical text-xs mb-4">{error}</div>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-accent-emerald hover:bg-accent-emeraldBright hover:text-base-void text-white transition-colors text-sm font-semibold rounded-md py-2.5 disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
