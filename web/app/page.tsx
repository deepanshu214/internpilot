import Link from "next/link";
import { ActionButton, BTN } from "@/components/client";
import { Card, Chip, Empty, PageHeader, ScoreBadge, sourceLabel, timeAgo } from "@/components/ui";
import { counts, inbox, parseList, sources, workerStatus } from "@/lib/data";
import { runTask, shortlist, skip } from "./actions";

export const dynamic = "force-dynamic";

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3">
      <p className="text-xs text-ink-2">{label}</p>
      <p className="tabular mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

export default async function Inbox({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const minScore = Number(sp.min ?? 60);
  const [rows, src, c, worker] = await Promise.all([
    inbox({ minScore, source: sp.source || undefined, q: sp.q || undefined }), sources(), counts(), workerStatus(),
  ]);
  const m = c.matches, o = c.outreach;
  const active = (m.shortlisted ?? 0) + (m.tailored ?? 0);
  const sent = (o.sent ?? 0) + (o.replied ?? 0);

  return (
    <>
      <PageHeader
        title="Inbox"
        sub={worker.lastRun ? `Last discovery ${timeAgo(worker.lastRun.ts)}. New matches, best first.` : "New matches, best first."}
        actions={<ActionButton action={runTask.bind(null, "discover", null, {})} pending="Queued…"
          title="Runs on your Mac worker">Find new jobs now</ActionButton>}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="New matches" value={m.new ?? 0} />
        <Stat label="Being prepared" value={active} />
        <Stat label="Applied" value={(m.applied ?? 0) + (m.oa ?? 0) + (m.interview ?? 0) + (m.offer ?? 0)} />
        <Stat label="Interviews" value={(m.interview ?? 0) + (m.offer ?? 0)} hint={m.offer ? `${m.offer} offer` : undefined} />
        <Stat label="Drafts to review" value={o.draft ?? 0} />
        <Stat label="Reply rate" value={sent ? `${Math.round((100 * (o.replied ?? 0)) / sent)}%` : "—"} hint={`${sent} sent`} />
      </div>

      <form className="mb-4 flex flex-wrap items-end gap-2 text-sm" method="get">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-ink-2">Search</span>
          <input name="q" defaultValue={sp.q} placeholder="Title or company"
            className="w-56 rounded-lg border border-line bg-surface px-3 py-1.5" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-ink-2">Source</span>
          <select name="source" defaultValue={sp.source ?? ""} className="rounded-lg border border-line bg-surface px-2 py-1.5">
            <option value="">All sources</option>
            {src.map((s) => <option key={s.source} value={s.source}>{sourceLabel(s.source)} ({s.n})</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-ink-2">Min score</span>
          <select name="min" defaultValue={String(minScore)} className="rounded-lg border border-line bg-surface px-2 py-1.5">
            {[0, 50, 60, 70, 80, 85].map((v) => <option key={v} value={v}>{v}+</option>)}
          </select>
        </label>
        <button className={BTN.secondary}>Apply filters</button>
      </form>

      <Card>
        {rows.length === 0 ? (
          <Empty>No new matches at this score. Lower the minimum, or run discovery.</Empty>
        ) : (
          <ul className="divide-y divide-line">
            {rows.map((r) => {
              const reasons = parseList(r.reasons).filter((x) => !x.startsWith("Pitch:"));
              const gaps = parseList(r.missing_skills);
              return (
                <li key={r.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-start">
                  <ScoreBadge score={Number(r.score)} method={r.method} />
                  <div className="min-w-0 flex-1">
                    <Link href={`/jobs/${r.id}`} className="font-medium hover:text-accent-ink hover:underline">{r.title}</Link>
                    <p className="mt-0.5 text-sm text-ink-2">
                      {r.company} · {r.location || "—"}{r.remote ? " · Remote" : ""}
                      <span className="text-ink-3"> · {sourceLabel(r.source)} · {timeAgo(r.posted_at || r.first_seen)}</span>
                    </p>
                    {reasons[0] && <p className="mt-1 text-sm text-ink-2">{reasons[0]}</p>}
                    {gaps.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1">
                        <span className="text-xs text-ink-3">Gaps:</span>
                        {gaps.slice(0, 5).map((g) => <Chip key={g} tone="gap">{g}</Chip>)}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <ActionButton action={shortlist.bind(null, r.id)} variant="primary" pending="Queued…"
                      title="Tailor resume, find contacts and draft emails">Shortlist & prepare</ActionButton>
                    <ActionButton action={skip.bind(null, r.id)} variant="ghost" pending="…">Skip</ActionButton>
                    <a href={r.url} target="_blank" rel="noreferrer" className={BTN.ghost}>Posting ↗</a>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
