import Link from "next/link";
import { Card, CardHeader, Empty, PageHeader, timeAgo } from "@/components/ui";
import { llmUsage, recentEvents, recentTasks, workerStatus } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function Activity() {
  const [tasks, events, worker, ai] = await Promise.all([recentTasks(), recentEvents(), workerStatus(), llmUsage()]);
  const providers = Object.entries(ai.caps).filter(([, c]) => c.max_requests_per_day);
  const weekCalls = ai.week.reduce((a, d) => a + Object.values(d.usage).reduce((b, u) => b + u.requests, 0), 0);
  return (
    <>
      <PageHeader title="Activity" sub={worker.online ? `Worker online · heartbeat ${timeAgo(worker.heartbeat)}`
        : "Worker offline. Start it on your Mac: ./scripts/install_launchd.sh"} />
      <Card className="mb-4">
        <CardHeader title="AI usage & cost" aside={<span className="text-xs font-semibold text-good-ink">Cost: $0.00 · free tiers only</span>} />
        <div className="px-4 py-3 text-sm">
          {ai.paidWarning && (
            <p role="alert" className="mb-3 rounded-lg border border-critical px-3 py-2 text-critical">
              ⚠ Groq reported paid-plan limits. Check console.groq.com/settings/billing and remove any payment method.
            </p>
          )}
          {providers.length === 0 ? <p className="text-ink-3">No usage yet. The worker publishes its caps when it starts.</p> : (
            <table className="tabular w-full">
              <thead><tr className="text-left text-xs text-ink-3"><th className="py-1 font-medium">Provider</th>
                <th className="py-1 font-medium">Requests today</th><th className="py-1 font-medium">Tokens today</th>
                <th className="py-1 font-medium">Status</th></tr></thead>
              <tbody className="divide-y divide-line">
                {providers.map(([name, cap]) => {
                  const u = ai.today[name] ?? { requests: 0, tokens: 0, limited: false };
                  const frac = Math.max(u.requests / (cap.max_requests_per_day || Infinity), u.tokens / (cap.max_tokens_per_day || Infinity));
                  return (
                    <tr key={name}>
                      <td className="py-1.5">{name}<span className="block text-xs text-ink-3">{cap.model || "auto"}</span></td>
                      <td className="py-1.5">{u.requests} / {cap.max_requests_per_day}</td>
                      <td className="py-1.5">{u.tokens.toLocaleString()} / {cap.max_tokens_per_day?.toLocaleString()}</td>
                      <td className="py-1.5 text-xs">{!cap.configured ? <span className="text-ink-3">no key</span>
                        : u.limited || frac >= 1 ? <span className="text-critical">✕ capped for today</span>
                        : frac >= 0.8 ? <span className="text-ink">⚠ {Math.round(frac * 100)}%</span>
                        : <span className="text-good-ink">✓ {Math.round(frac * 100)}%</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <p className="mt-2 text-xs text-ink-3">
            {weekCalls} AI calls in the last 7 days. Caps sit below each provider&apos;s free limit; when one is hit the bot
            switches to the next free provider, then to keyword scoring and templates. It never pays for more.
          </p>
        </div>
      </Card>
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
