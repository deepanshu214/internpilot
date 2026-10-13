import Link from "next/link";
import { BarList, Columns } from "@/components/charts";
import { Card, CardHeader, Empty, PageHeader, sourceLabel } from "@/components/ui";
import { query } from "@/lib/db";
import { parseList } from "@/lib/data";

export const dynamic = "force-dynamic";
const ORDER = ["shortlisted", "tailored", "applied", "oa", "interview", "offer"];

function weekStart(d: Date) {
  const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  x.setUTCDate(x.getUTCDate() - ((x.getUTCDay() + 6) % 7));
  return x;
}

export default async function Insights() {
  const [statuses, applied, bySource, top, outreach, deadlines, reports] = await Promise.all([
    query<{ status: string; n: number }>("select status, count(*) n from matches group by status"),
    query<{ applied_at: string }>("select applied_at from matches where applied_at is not null"),
    query<{ source: string; n: number; good: number }>(`select j.source, count(*) n, sum(case when m.score >= 70 then 1 else 0 end) good
      from jobs j join matches m on m.job_id = j.id group by j.source order by good desc, n desc limit 12`),
    query<{ missing_skills: string }>("select missing_skills from matches order by score desc limit 60"),
    query<{ variant: string | null; project_pitched: string | null; status: string }>(
      "select variant, project_pitched, status from outreach where kind = 'cold' and status in ('sent', 'replied')"),
    query<{ title: string; company: string; deadline: string; status: string; id: string }>(`select j.id, j.title, j.company, m.deadline, m.status
      from matches m join jobs j on j.id = m.job_id where m.deadline is not null and m.status not in ('skipped','rejected')
      order by m.deadline limit 10`),
    query<{ id: string; title: string; content: string }>("select id, title, content from documents where kind = 'weekly_report' order by created_at desc limit 4"),
  ]);

  const by = Object.fromEntries(statuses.map((s) => [s.status, Number(s.n)]));
  const reached = (stage: string) => ORDER.slice(ORDER.indexOf(stage)).reduce((a, s) => a + (by[s] ?? 0), 0)
    + (ORDER.indexOf(stage) <= ORDER.indexOf("applied") ? (by.rejected ?? 0) : 0);
  const funnel = [
    { label: "Matched", value: Object.values(by).reduce((a, b) => a + b, 0) },
    { label: "Shortlisted", value: reached("shortlisted") },
    { label: "Applied", value: reached("applied") },
    { label: "Assessment", value: reached("oa") },
    { label: "Interview", value: reached("interview") },
    { label: "Offer", value: reached("offer") },
  ];

  const thisWeek = weekStart(new Date());
  const weeks = Array.from({ length: 8 }, (_, i) => {
    const d = new Date(thisWeek);
    d.setUTCDate(d.getUTCDate() - 7 * (7 - i));
    return d;
  });
  const perWeek = weeks.map((w) => ({
    label: w.toISOString().slice(5, 10),
    value: applied.filter((a) => weekStart(new Date(a.applied_at)).getTime() === w.getTime()).length,
  }));

  const gapCounts = new Map<string, number>();
  top.forEach((r) => parseList(r.missing_skills).forEach((s) => gapCounts.set(s, (gapCounts.get(s) ?? 0) + 1)));
  const gaps = [...gapCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value }));

  const rate = (rows: typeof outreach, key: "variant" | "project_pitched") => {
    const m = new Map<string, { sent: number; replied: number }>();
    rows.forEach((o) => {
      const k = (o[key] ?? "—").split(" — ")[0];
      const v = m.get(k) ?? { sent: 0, replied: 0 };
      v.sent++;
      if (o.status === "replied") v.replied++;
      m.set(k, v);
    });
    return [...m.entries()].map(([k, v]) => ({ label: key === "variant" ? `Template ${k}` : k,
      value: Math.round((100 * v.replied) / v.sent), hint: `${v.replied}/${v.sent} replied` }));
  };

  return (
    <>
      <PageHeader title="Insights" sub="What's working, and what to learn next." />
      <div className="grid gap-4 md:grid-cols-2">
        <Card><CardHeader title="Funnel" /><div className="px-4 py-3"><BarList data={funnel} unit="jobs" /></div></Card>
        <Card><CardHeader title="Applications per week" /><div className="px-4 py-3"><Columns data={perWeek} unit="applications" /></div></Card>
        <Card><CardHeader title="Good matches (70+) by source" />
          <div className="px-4 py-3"><BarList data={bySource.map((s) => ({ label: sourceLabel(s.source), value: Number(s.good), hint: `${s.n} total` }))} unit="matches" /></div></Card>
        <Card><CardHeader title="Skills to learn next" aside={<span className="text-xs text-ink-3">missing in your top 60 matches</span>} />
          <div className="px-4 py-3"><BarList data={gaps} unit="jobs ask for it" empty="No gaps detected yet." /></div></Card>
        <Card><CardHeader title="Cold email reply rate by template" />
          <div className="px-4 py-3"><BarList data={rate(outreach, "variant")} unit="% replied" empty="Send a few emails to compare templates." /></div></Card>
        <Card><CardHeader title="Reply rate by project pitched" />
          <div className="px-4 py-3"><BarList data={rate(outreach, "project_pitched")} unit="% replied" empty="No sent emails yet." /></div></Card>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Deadlines" />
          {deadlines.length === 0 ? <Empty>No deadlines tracked. OA invites add them automatically.</Empty> : (
            <ul className="divide-y divide-line text-sm">{deadlines.map((d) => (
              <li key={d.id} className="flex gap-3 px-4 py-2"><span className="tabular w-20 shrink-0 text-ink-2">{d.deadline.slice(0, 10)}</span>
                <Link href={`/jobs/${d.id}`} className="truncate hover:underline">{d.title} @ {d.company}</Link></li>))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Weekly reviews" />
          {reports.length === 0 ? <Empty>The first weekly review arrives Sunday night.</Empty> : (
            <div className="divide-y divide-line">{reports.map((r) => (
              <details key={r.id} className="px-4 py-2 text-sm"><summary className="cursor-pointer font-medium">{r.title}</summary>
                <pre className="mt-1 whitespace-pre-wrap font-sans text-ink-2">{r.content}</pre></details>))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
