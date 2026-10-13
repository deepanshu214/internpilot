import Link from "next/link";
import { StatusSelect } from "@/components/client";
import { PageHeader, StatusBadge, statusLabel, timeAgo } from "@/components/ui";
import { pipeline, STATUSES } from "@/lib/data";
import { moveStatus } from "../actions";

export const dynamic = "force-dynamic";
const COLUMNS = ["shortlisted", "tailored", "applied", "oa", "interview", "offer", "rejected"];
const OPTIONS = STATUSES.map((s) => ({ value: s, label: statusLabel(s) }));

export default async function Pipeline() {
  const rows = await pipeline();
  return (
    <>
      <PageHeader title="Pipeline" sub="Everything you're pursuing. Inbox tracking moves cards when emails arrive; you can move them too." />
      <div className="-mx-4 overflow-x-auto px-4 pb-2">
        <div className="grid min-w-[1050px] grid-cols-7 gap-3">
          {COLUMNS.map((col) => {
            const items = rows.filter((r) => r.status === col);
            return (
              <section key={col} aria-label={statusLabel(col)} className="flex min-w-0 flex-col gap-2">
                <div className="flex items-center justify-between px-1">
                  <StatusBadge status={col} />
                  <span className="tabular text-xs text-ink-3">{items.length}</span>
                </div>
                <div className="flex min-h-24 flex-col gap-2 rounded-xl bg-surface-2/60 p-1.5">
                  {items.map((r) => (
                    <article key={r.id} className="rounded-lg border border-line bg-surface p-2.5">
                      <Link href={`/jobs/${r.id}`} className="line-clamp-2 text-sm font-medium hover:underline">{r.title}</Link>
                      <p className="mt-0.5 truncate text-xs text-ink-2">{r.company}</p>
                      <div className="mt-2 flex items-center justify-between gap-1 text-xs text-ink-3">
                        <span className="tabular">{r.score}</span>
                        <span>{r.deadline ? `due ${r.deadline.slice(5, 10)}` : timeAgo(r.updated_at)}</span>
                      </div>
                      <div className="mt-2">
                        <StatusSelect action={moveStatus.bind(null, r.id)} value={r.status} options={OPTIONS} />
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </>
  );
}
