"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

type NavItem = { label: string; href?: string; phase?: 2 | 3 | 4 | 5 };
type NavSection = { title: string; items: NavItem[] };

const SECTIONS: NavSection[] = [
  {
    title: "Command",
    items: [
      { label: "Dashboard", href: "/dashboard" },
      { label: "Projects", href: "/projects" },
      { label: "Approvals", href: "/approvals" },
    ],
  },
  {
    title: "Engineering",
    items: [
      { label: "Tasks", phase: 2 },
      { label: "Code", phase: 2 },
      { label: "Reviews", phase: 2 },
      { label: "Tests", phase: 3 },
    ],
  },
  {
    title: "Economics",
    items: [
      { label: "Costs", href: "/costs" },
      { label: "Tokens", phase: 2 },
      { label: "Budgets", phase: 3 },
      { label: "Model Efficiency", phase: 3 },
    ],
  },
  {
    title: "Observability",
    items: [
      { label: "Events", href: "/events" },
      { label: "Logs", phase: 4 },
      { label: "Metrics", phase: 4 },
      { label: "Alerts", phase: 4 },
    ],
  },
  {
    title: "Models",
    items: [
      { label: "Models", href: "/models" },
      { label: "Providers", phase: 4 },
    ],
  },
  {
    title: "Security",
    items: [
      { label: "Security Center", phase: 3 },
      { label: "Red Team", phase: 3 },
      { label: "Blue Team", phase: 3 },
      { label: "Findings", phase: 3 },
    ],
  },
  {
    title: "Infrastructure",
    items: [
      { label: "Servers", phase: 4 },
      { label: "Containers", phase: 4 },
      { label: "Services", phase: 4 },
      { label: "Network", phase: 4 },
    ],
  },
  {
    title: "Governance",
    items: [
      { label: "Policies", phase: 2 },
      { label: "Audit", phase: 3 },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  // The map of where this is going is worth seeing, but not at the cost of burying the six
  // screens that actually work - so it is opt-in rather than 22 permanent dead links.
  const [showPlanned, setShowPlanned] = useState(false);

  const sections = SECTIONS.map((s) => ({
    ...s,
    items: showPlanned ? s.items : s.items.filter((i) => i.href),
  })).filter((s) => s.items.length > 0);

  const plannedCount = SECTIONS.reduce((n, s) => n + s.items.filter((i) => !i.href).length, 0);

  return (
    <aside className="w-60 shrink-0 h-screen sticky top-0 overflow-y-auto bg-base-near border-r border-base-border flex flex-col">
      <div className="px-5 pt-5 pb-6">
        <Link href="/dashboard" className="block group">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-emeraldBright live-dot" />
            <span className="text-[13px] font-semibold tracking-[0.14em] text-neutral-100 group-hover:text-white">
              PHOENIX FORGE
            </span>
          </div>
          <div className="text-2xs text-neutral-600 mt-1 ml-3.5">AI Command Center</div>
        </Link>
      </div>

      <nav className="flex-1 px-2.5 pb-4">
        {sections.map((section) => (
          <div key={section.title} className="mb-5">
            <div className="px-2.5 text-2xs font-medium uppercase tracking-[0.13em] text-neutral-600 mb-1.5">
              {section.title}
            </div>
            <div className="flex flex-col gap-px">
              {section.items.map((item) =>
                item.href ? (
                  <NavLink key={item.label} item={item} active={!!pathname?.startsWith(item.href)} />
                ) : (
                  <PlannedItem key={item.label} item={item} />
                ),
              )}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-2.5 pb-4 border-t border-base-border pt-3">
        <button
          onClick={() => setShowPlanned(!showPlanned)}
          className="w-full text-left px-2.5 py-1.5 rounded text-2xs text-neutral-600 hover:text-neutral-400 transition-colors flex items-center justify-between"
        >
          <span>{showPlanned ? "Hide roadmap" : "Show roadmap"}</span>
          <span className="text-neutral-700 num">{plannedCount}</span>
        </button>
      </div>
    </aside>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href!}
      className={`relative px-2.5 py-1.5 rounded text-[13px] transition-colors ${
        active
          ? "bg-accent-emerald/15 text-emerald-300 font-medium"
          : "text-neutral-400 hover:bg-base-graphite hover:text-neutral-200"
      }`}
    >
      {active && (
        <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-accent-emeraldBright" />
      )}
      {item.label}
    </Link>
  );
}

function PlannedItem({ item }: { item: NavItem }) {
  return (
    <span
      className="px-2.5 py-1.5 rounded text-[13px] text-neutral-700 cursor-default flex items-center justify-between"
      title={`Planned for phase ${item.phase}`}
    >
      {item.label}
      <span className="text-2xs text-neutral-700 border border-base-border rounded px-1 num">
        P{item.phase}
      </span>
    </span>
  );
}
