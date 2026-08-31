"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "./Sidebar";
import { api, clearToken, getToken } from "@/lib/api";

type Me = { id: string; email: string };

export function AppShell({
  children,
  title,
  subtitle,
  actions,
}: {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  // Runs once. It previously depended on the router object, which is not a stable identity -
  // the effect re-fired on every render, so each render started another /auth/me and set
  // state again, and the page spun until the tab locked up.
  useEffect(() => {
    if (!getToken()) {
      window.location.assign("/login");
      return;
    }
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => {
        clearToken();
        window.location.assign("/login");
      })
      .finally(() => setChecked(true));
  }, []);

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-2 text-neutral-600 text-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-emeraldBright live-dot" />
          Loading
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-base-black">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 shrink-0 border-b border-base-border flex items-center gap-4 px-7 sticky top-0 bg-base-black/85 backdrop-blur z-10">
          <div className="flex-1 min-w-0">
            {title && (
              <h1 className="text-[15px] font-semibold text-neutral-100 leading-tight truncate">{title}</h1>
            )}
            {subtitle && <p className="text-2xs text-neutral-500 truncate">{subtitle}</p>}
          </div>
          {actions}
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-2xs text-neutral-600 hidden sm:block">{me?.email}</span>
            <button
              onClick={() => {
                clearToken();
                window.location.assign("/login");
              }}
              className="text-2xs text-neutral-500 hover:text-neutral-200 border border-base-border hover:border-base-borderStrong rounded px-2 py-1 transition-colors"
            >
              Sign out
            </button>
          </div>
        </header>
        <main className="flex-1 min-w-0 p-7">{children}</main>
      </div>
    </div>
  );
}
