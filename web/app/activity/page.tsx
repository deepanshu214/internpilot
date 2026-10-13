import Link from "next/link";
import { Card, CardHeader, Empty, PageHeader, timeAgo } from "@/components/ui";
import { recentEvents, recentTasks, workerStatus } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function Activity() {
  const [tasks, events, worker] = await Promise.all([recentTasks(), recentEvents(), workerStatus()]);
  return (
    <>
      <PageHeader title="Activity" sub={worker.online ? `Worker online · heartbeat ${timeAgo(worker.heartbeat)}`
        : "Worker offline. Start it on your Mac: ./scripts/install_launchd.sh"} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Tasks" />
          {tasks.length === 0 ? <Empty>No tasks yet.</Empty> : (
            <ul className="divide-y divide-line text-sm">{tasks.map((t) => (
              <li key={t.id} className="px-4 py-2">
                <span className="font-medium">{t.kind}</span>{" "}
                <span className={t.status === "failed" ? "text-critical" : "text-ink-3"}>{t.status}</span>
                <span className="text-ink-3"> · {timeAgo(t.created_at)}</span>
                {t.job_id && <Link href={`/jobs/${t.job_id}`} className="block truncate text-xs text-ink-2 hover:underline">{t.title} @ {t.company}</Link>}
                {t.error && <p className="text-xs text-critical">{t.error}</p>}
              </li>))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Event log" />
          <ul className="divide-y divide-line text-sm">{events.map((e) => (
            <li key={e.id} className="px-4 py-2">
              <span className="text-xs text-ink-3">{timeAgo(e.ts)} · {e.kind}</span>
              <p className="line-clamp-2 text-ink-2">{e.title ? `${e.title}: ` : ""}{e.detail}</p>
            </li>))}
          </ul>
        </Card>
      </div>
    </>
  );
}
