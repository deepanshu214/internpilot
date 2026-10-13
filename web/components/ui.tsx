import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-line bg-surface ${className}`}>{children}</section>;
}

export function CardHeader({ title, aside }: { title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
      <h2 className="text-sm font-semibold">{title}</h2>
      {aside}
    </div>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-ink-2">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function ScoreBadge({ score, method }: { score: number; method?: string | null }) {
  const strong = score >= 85, mid = score >= 70;
  return (
    <span
      title={method === "heuristic" ? "Keyword score (no LLM read yet)" : `Scored by ${method ?? "LLM"}`}
      className={`tabular inline-flex h-9 w-11 shrink-0 items-center justify-center rounded-lg text-sm font-semibold ${
        strong ? "bg-accent text-white" : mid ? "bg-accent-soft text-accent-ink" : "bg-surface-2 text-ink-2"}`}>
      {score}
    </span>
  );
}

const STATUS_META: Record<string, { label: string; icon: string; tone: string }> = {
  new: { label: "New", icon: "•", tone: "text-ink-2" },
  shortlisted: { label: "Shortlisted", icon: "☆", tone: "text-accent-ink" },
  tailored: { label: "Ready to apply", icon: "✎", tone: "text-accent-ink" },
  applied: { label: "Applied", icon: "↗", tone: "text-ink" },
  oa: { label: "Assessment", icon: "⧗", tone: "text-ink" },
  interview: { label: "Interview", icon: "✓", tone: "text-good-ink" },
  offer: { label: "Offer", icon: "★", tone: "text-good-ink" },
  rejected: { label: "Rejected", icon: "✕", tone: "text-critical" },
  skipped: { label: "Skipped", icon: "–", tone: "text-ink-3" },
};
export const statusLabel = (s: string) => STATUS_META[s]?.label ?? s;

export function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status, icon: "•", tone: "text-ink-2" };
  const dot = { oa: "bg-warning", interview: "bg-good", offer: "bg-good", rejected: "bg-critical" }[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs font-medium ${m.tone}`}>
      {dot ? <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden /> : <span aria-hidden>{m.icon}</span>}
      {m.label}
    </span>
  );
}

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "gap" | "accent" }) {
  const cls = { neutral: "bg-surface-2 text-ink-2", gap: "border border-dashed border-line-strong text-ink-2", accent: "bg-accent-soft text-accent-ink" }[tone];
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs ${cls}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-4 py-8 text-center text-sm text-ink-3">{children}</p>;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (Number.isNaN(s)) return "—";
  if (s < 0) {
    const d = Math.round(-s / 86400);
    return d <= 0 ? "today" : `in ${d}d`;
  }
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const sourceLabel = (s: string) =>
  s.replace(/^jobspy:/, "").replace(/^gmail:/, "").replace(/^\w/, (c) => c.toUpperCase());
