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
    <div className="min-h-screen flex items-center justify-center bg-base-black">
      <form onSubmit={handleSubmit} className="w-full max-w-sm bg-base-near border border-base-border rounded-lg p-8">
        <div className="text-emerald-500 font-bold tracking-wide mb-1">PHOENIX FORGE</div>
        <div className="text-neutral-500 text-xs mb-6">AI Engineering & Infrastructure Command Center</div>

        <label className="block text-xs text-neutral-400 mb-1">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full mb-4 bg-base-dark border border-base-border rounded px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-accent-emeraldBright"
        />

        <label className="block text-xs text-neutral-400 mb-1">Password</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-6 bg-base-dark border border-base-border rounded px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-accent-emeraldBright"
        />

        {error && <div className="text-status-critical text-xs mb-4">{error}</div>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-accent-emerald hover:bg-accent-emeraldBright transition-colors text-sm font-medium rounded py-2 disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
