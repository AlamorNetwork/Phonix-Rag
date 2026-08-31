"use client";

import Link from "next/link";

export const ROLE_HUE: Record<string, string> = {
  manager: "text-role-manager border-role-manager/30 bg-role-manager/10",
  architect: "text-role-architect border-role-architect/30 bg-role-architect/10",
  coder: "text-role-coder border-role-coder/30 bg-role-coder/10",
  reviewer: "text-role-reviewer border-role-reviewer/30 bg-role-reviewer/10",
};

export const ROLE_DOT: Record<string, string> = {
  manager: "bg-role-manager",
  architect: "bg-role-architect",
  coder: "bg-role-coder",
  reviewer: "bg-role-reviewer",
};

export const RISK_HUE: Record<string, string> = {
  READ: "text-status-info border-status-info/30 bg-status-info/10",
  LOW: "text-status-success border-status-success/30 bg-status-success/10",
  MEDIUM: "text-status-warning border-status-warning/30 bg-status-warning/10",
  HIGH: "text-status-critical border-status-critical/30 bg-status-critical/10",
  CRITICAL: "text-status-critical border-status-critical/60 bg-status-critical/20 font-semibold",
};

export const STATE_HUE: Record<string, string> = {
  done: "text-status-success border-status-success/30",
  completed: "text-status-success border-status-success/30",
  running: "text-status-warning border-status-warning/30",
  queued: "text-status-warning border-status-warning/30",
  in_review: "text-role-reviewer border-role-reviewer/30",
  executing: "text-accent-emeraldBright border-accent-emeraldBright/30",
  plan_proposed: "text-accent-irisBright border-accent-irisBright/40",
  rejected: "text-status-critical border-status-critical/30",
  blocked: "text-status-critical border-status-critical/30",
  failed: "text-status-critical border-status-critical/30",
  timeout: "text-status-critical border-status-critical/30",
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
  accent,
}: {
  title?: string;
  note?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  accent?: "teal" | "iris" | "warning";
}) {
  const rail =
    accent === "teal"
      ? "before:bg-accent-emeraldBright"
      : accent === "iris"
        ? "before:bg-accent-irisBright"
        : accent === "warning"
          ? "before:bg-status-warning"
          : "";

  return (
    <section
      className={`relative bg-base-near border border-base-border rounded-xl shadow-panel bg-panel-sheen overflow-hidden ${
        accent
          ? `before:absolute before:inset-y-0 before:left-0 before:w-[2px] before:content-[''] ${rail}`
          : ""
      } ${className}`}
    >
      {title && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-base-border/70">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold text-neutral-100 tracking-tight leading-tight">
              {title}
            </h2>
            {note && <p className="text-2xs text-neutral-500 mt-0.5">{note}</p>}
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
      className={`text-2xs uppercase tracking-[0.09em] border rounded-md px-1.5 py-0.5 whitespace-nowrap ${
        tone || "text-neutral-500 border-base-border"
      }`}
    >
      {label.replace(/_/g, " ")}
    </span>
  );
}

/** A tiny area chart. Trend is the part of a number you can act on — whether spend is
 *  accelerating matters more than what it currently totals. */
export function Sparkline({
  values,
  stroke = "#22c99f",
  height = 34,
}: {
  values: number[];
  stroke?: string;
  height?: number;
}) {
  if (values.length < 2) {
    return <div style={{ height }} className="w-full rounded bg-base-dark/40" />;
  }

  const width = 100;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);

  const points = values.map((v, i) => [i * step, height - ((v - min) / span) * (height - 4) - 2]);
  const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const [lastX, lastY] = points[points.length - 1];
  const id = `spark-${stroke.replace("#", "")}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <circle cx={lastX} cy={lastY} r="2" fill={stroke} />
    </svg>
  );
}

export function Metric({
  label,
  value,
  sub,
  tone = "text-neutral-50",
  href,
  spark,
  sparkColor,
  urgent,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
  href?: string;
  spark?: number[];
  sparkColor?: string;
  urgent?: boolean;
}) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="text-2xs uppercase tracking-[0.13em] text-neutral-500">{label}</div>
        {urgent && <span className="w-1.5 h-1.5 rounded-full bg-status-warning live-dot mt-1" />}
      </div>
      <div className={`text-[1.75rem] font-semibold num leading-none mt-2 tracking-tight ${tone}`}>
        {value}
      </div>
      {sub && <div className="text-2xs text-neutral-500 mt-1.5">{sub}</div>}
      {spark && spark.length > 1 && (
        <div className="mt-2 -mx-1">
          <Sparkline values={spark} stroke={sparkColor} height={30} />
        </div>
      )}
    </>
  );

  const shell = `relative bg-base-near border rounded-xl shadow-panel bg-panel-sheen px-4 py-3.5 block transition-colors ${
    urgent ? "border-status-warning/40" : "border-base-border"
  }`;

  return href ? (
    <Link href={href} className={`${shell} hover:border-base-borderStrong`}>
      {body}
    </Link>
  ) : (
    <div className={shell}>{body}</div>
  );
}

/** Segmented progress: done / blocked / remaining, readable as a shape before the numbers. */
export function TaskBar({ total, done, blocked }: { total: number; done: number; blocked: number }) {
  if (total === 0) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="h-1.5 w-full bg-base-dark rounded-full overflow-hidden flex gap-px">
      <div className="bg-accent-emeraldBright transition-all" style={{ width: pct(done) }} />
      <div className="bg-status-critical transition-all" style={{ width: pct(blocked) }} />
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
      {unit}
    </span>
  );
}
