"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useFormStatus } from "react-dom";
import type { ReactNode } from "react";

const base = "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50";
export const BTN = {
  primary: `${base} bg-accent text-white hover:opacity-90`,
  secondary: `${base} border border-line-strong bg-surface hover:bg-surface-2`,
  ghost: `${base} text-ink-2 hover:bg-surface-2 hover:text-ink`,
  danger: `${base} border border-line text-critical hover:bg-surface-2`,
};

export function Submit({ children, variant = "secondary", pending = "Working…", title }:
  { children: ReactNode; variant?: keyof typeof BTN; pending?: string; title?: string }) {
  const { pending: busy } = useFormStatus();
  return (
    <button type="submit" disabled={busy} className={BTN[variant]} title={title} aria-busy={busy}>
      {busy ? pending : children}
    </button>
  );
}

/** One-button form bound to a server action. */
export function ActionButton({ action, children, variant = "secondary", pending, title }:
  { action: () => Promise<void>; children: ReactNode; variant?: keyof typeof BTN; pending?: string; title?: string }) {
  return (
    <form action={action}>
      <Submit variant={variant} pending={pending} title={title}>{children}</Submit>
    </form>
  );
}

export function StatusSelect({ action, value, options }:
  { action: (status: string) => Promise<void>; value: string; options: { value: string; label: string }[] }) {
  return (
    <select
      aria-label="Move to stage"
      defaultValue={value}
      onChange={(e) => action(e.target.value)}
      className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink-2">
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

const NAV = [
  { href: "/", label: "Inbox" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/outreach", label: "Outreach" },
  { href: "/insights", label: "Insights" },
  { href: "/activity", label: "Activity" },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col">
      {NAV.map((n) => {
        const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${active ? "bg-surface-2 font-semibold text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}
