import Link from "next/link";
import { Card, Empty, PageHeader, timeAgo } from "@/components/ui";
import { outreachList } from "@/lib/data";

export const dynamic = "force-dynamic";
const TABS = [["draft", "Drafts"], ["approved", "Sending"], ["sent", "Sent"], ["replied", "Replied"], ["all", "All"]];

export default async function OutreachPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const status = (await searchParams).status ?? "draft";
  const rows = await outreachList(status);
  return (
    <>
      <PageHeader title="Outreach" sub="Cold emails and follow-ups. Drafts are edited and approved on each job's page." />
      <nav aria-label="Filter" className="mb-3 flex gap-1 overflow-x-auto">
        {TABS.map(([v, label]) => (
          <Link key={v} href={`/outreach?status=${v}`} aria-current={status === v ? "page" : undefined}
            className={`rounded-lg px-3 py-1.5 text-sm ${status === v ? "bg-surface-2 font-semibold" : "text-ink-2 hover:bg-surface-2"}`}>{label}</Link>
        ))}
      </nav>
      <Card>
        {rows.length === 0 ? <Empty>Nothing here.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-xs text-ink-3">
                <th className="px-4 py-2 font-medium">Job</th><th className="px-4 py-2 font-medium">To</th>
                <th className="px-4 py-2 font-medium">Subject</th><th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">When</th></tr></thead>
              <tbody className="divide-y divide-line">
                {rows.map((o) => (
                  <tr key={o.id}>
                    <td className="max-w-56 px-4 py-2"><Link href={`/jobs/${o.job_id}`} className="line-clamp-1 hover:underline">{o.title ?? "—"}</Link>
                      <span className="text-xs text-ink-3">{o.company}</span></td>
                    <td className="px-4 py-2 text-ink-2">{o.to_email ?? <span className="text-ink-3">no recipient</span>}</td>
                    <td className="max-w-72 px-4 py-2"><span className="line-clamp-1">{o.kind === "followup" ? "↻ " : ""}{o.subject}</span></td>
                    <td className="px-4 py-2 text-ink-2">{o.status}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-ink-3">{timeAgo(o.sent_at ?? o.created_at)}
                      {o.followup_due && o.status === "sent" ? ` · follow-up ${timeAgo(o.followup_due)}` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
