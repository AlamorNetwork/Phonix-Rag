"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { api, clearToken, getToken } from "@/lib/api";

type Me = { id: string; email: string };

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => {
        clearToken();
        router.replace("/login");
      })
      .finally(() => setChecked(true));
  }, [router]);

  if (!checked) {
    return <div className="min-h-screen flex items-center justify-center text-neutral-500 text-sm">Loading…</div>;
  }

  return (
    <div className="flex min-h-screen bg-base-black">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 border-b border-base-border flex items-center justify-end px-6 gap-4">
          <span className="text-xs text-neutral-500">{me?.email}</span>
          <button
            onClick={() => {
              clearToken();
              router.replace("/login");
            }}
            className="text-xs text-neutral-400 hover:text-neutral-200 border border-base-border rounded px-2 py-1"
          >
            Sign out
          </button>
        </header>
        <main className="flex-1 min-w-0 p-6 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
