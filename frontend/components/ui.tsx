"use client";

import Link from "next/link";

export const ROLE_HUE: Record<string, string> = {
  manager: "text-role-manager border-role-manager/35 bg-role-manager/10",
  architect: "text-role-architect border-role-architect/35 bg-role-architect/10",
  coder: "text-role-coder border-role-coder/35 bg-role-coder/10",
  reviewer: "text-role-reviewer border-role-reviewer/35 bg-role-reviewer/10",
};

export const RISK_HUE: Record<string, string> = {
  READ: "text-status-info border-status-info/35 bg-status-info/10",
  LOW: "text-status-success border-status-success/35 bg-status-success/10",
  MEDIUM: "text-status-warning border-status-warning/35 bg-status-warning/10",
  HIGH: "text-status-critical border-status-critical/35 bg-status-critical/10",
  CRITICAL: "text-status-critical border-status-critical/60 bg-status-critical/20 font-semibold",
};

export const STATE_HUE: Record<string, string> = {
  done: "text-status-success border-status-success/35",
  completed: "text-status-success border-status-success/35",
  running: "text-status-warning border-status-warning/35",
  queued: "text-status-warning border-status-warning/35",
  in_review: "text-role-reviewer border-role-reviewer/35",
  executing: "text-status-warning border-status-warning/35",
  plan_proposed: "text-role-manager border-role-manager/35",
  rejected: "text-status-critical border-status-critical/35",
  blocked: "text-status-critical border-status-critical/35",
  failed: "text-status-critical border-status-critical/35",
  timeout: "text-status-critical border-status-critical/35",
  draft: "text-neutral-500 border-base-border",
  pending: "text-neutral-500 border-base-border",
  planning: "text-neutral-500 border-base-border",
};

export function Panel({
  title,
  note,
  action,
  children,
  className = "",
}: {
  title?: string;
  note?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`bg-base-near border border-base-border rounded-lg shadow-panel overflow-hidden ${className}`}
    >
      {title && (
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-base-border">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold text-neutral-200 leading-tight">{title}</h2>
            {note && <p className="text-2xs text-neutral-600 mt-0.5">{note}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Chip({ label, tone = "" }: { label: string; tone?: string }) {
  return (
    <span
      className={`text-2xs uppercase tracking-wider border rounded px-1.5 py-0.5 whitespace-nowrap ${
        tone || "text-neutral-500 border-base-border"
      }`}
    >
      {label.replace(/_/g, " ")}
    </span>
  );
}

export function Metric({
  label,
  value,
  sub,
  tone = "text-neutral-100",
  href,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
  href?: string;
}) {
  const body = (
    <>
      <div className="text-2xs uppercase tracking-[0.12em] text-neutral-600 mb-1.5">{label}</div>
      <div className={`text-2xl font-semibold num leading-none ${tone}`}>{value}</div>
      {sub && <div className="text-2xs text-neutral-600 mt-1.5">{sub}</div>}
    </>
  );

  const shell =
    "bg-base-near border border-base-border rounded-lg shadow-panel px-4 py-3.5 block transition-colors";

  return href ? (
    <Link href={href} className={`${shell} hover:border-base-borderStrong`}>
      {body}
    </Link>
  ) : (
    <div className={shell}>{body}</div>
  );
}

/** Segmented progress: how much of a plan is done, blocked, or still to do — readable as a
 *  shape before you read the numbers. */
export function TaskBar({ total, done, blocked }: { total: number; done: number; blocked: number }) {
  if (total === 0) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="h-1 w-full bg-base-dark rounded-full overflow-hidden flex">
      <div className="bg-status-success" style={{ width: pct(done) }} />
      <div className="bg-status-critical" style={{ width: pct(blocked) }} />
    </div>
  );
}

export function TimeAgo({ iso }: { iso: string }) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  const [value, unit] =
    seconds < 60
      ? [Math.floor(seconds), "s"]
      : seconds < 3600
        ? [Math.floor(seconds / 60), "m"]
        : seconds < 86400
          ? [Math.floor(seconds / 3600), "h"]
          : [Math.floor(seconds / 86400), "d"];
  return (
    <span className="num" title={new Date(iso).toLocaleString()}>
      {value}
      {unit} ago
    </span>
  );
}
