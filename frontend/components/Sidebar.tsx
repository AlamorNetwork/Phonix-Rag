"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = { label: string; href?: string };
type NavSection = { title: string; items: NavItem[] };

const SECTIONS: NavSection[] = [
  { title: "COMMAND CENTER", items: [{ label: "Dashboard", href: "/dashboard" }] },
  {
    title: "PROJECTS",
    items: [
      { label: "Projects", href: "/projects" },
      { label: "Models" },
      { label: "Providers" },
    ],
  },
  { title: "ENGINEERING", items: [{ label: "Tasks" }, { label: "Code" }, { label: "Tests" }, { label: "Reviews" }] },
  {
    title: "SECURITY",
    items: [{ label: "Security Center" }, { label: "Red Team" }, { label: "Blue Team" }, { label: "Findings" }],
  },
  {
    title: "INFRASTRUCTURE",
    items: [{ label: "Servers" }, { label: "Containers" }, { label: "Services" }, { label: "Network" }],
  },
  {
    title: "OBSERVABILITY",
    items: [{ label: "Logs" }, { label: "Metrics" }, { label: "Events", href: "/events" }, { label: "Alerts" }],
  },
  {
    title: "GOVERNANCE",
    items: [{ label: "Approvals", href: "/approvals" }, { label: "Policies" }, { label: "Audit" }],
  },
  {
    title: "ECONOMICS",
    items: [{ label: "Costs", href: "/costs" }, { label: "Tokens" }, { label: "Budgets" }, { label: "Model Efficiency" }],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 shrink-0 h-screen overflow-y-auto bg-base-near border-r border-base-border px-3 py-4">
      <div className="px-2 mb-6">
        <div className="text-emerald-500 font-bold tracking-wide text-sm">PHOENIX FORGE</div>
        <div className="text-[10px] text-neutral-500 mt-0.5">AI Command Center</div>
      </div>

      {SECTIONS.map((section) => (
        <div key={section.title} className="mb-5">
          <div className="px-2 text-[10px] font-semibold tracking-wider text-neutral-600 mb-1.5">
            {section.title}
          </div>
          <nav className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const active = item.href && pathname?.startsWith(item.href);
              if (!item.href) {
                return (
                  <span
                    key={item.label}
                    className="px-2 py-1.5 rounded text-sm text-neutral-700 cursor-not-allowed flex items-center justify-between"
                    title="Not yet implemented (later phase)"
                  >
                    {item.label}
                    <span className="text-[9px] border border-neutral-800 rounded px-1 text-neutral-700">soon</span>
                  </span>
                );
              }
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={`px-2 py-1.5 rounded text-sm transition-colors ${
                    active
                      ? "bg-accent-emerald/20 text-emerald-400"
                      : "text-neutral-400 hover:bg-base-dark hover:text-neutral-200"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      ))}

      <div className="mt-6 px-2 text-[10px] text-neutral-500">
        <span className="opacity-70">Settings</span>
      </div>
    </aside>
  );
}
