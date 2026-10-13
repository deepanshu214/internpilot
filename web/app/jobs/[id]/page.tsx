import Link from "next/link";
import { notFound } from "next/navigation";
import { ActionButton, BTN, StatusSelect, Submit } from "@/components/client";
import { CopyButton, DraftEditor } from "@/components/editors";
import { Card, CardHeader, Chip, Empty, ScoreBadge, StatusBadge, sourceLabel, statusLabel, timeAgo } from "@/components/ui";
import { job as getJob, jobContacts, jobDocuments, jobOutreach, jobResumes, jobTasks, parseList, STATUSES } from "@/lib/data";
import { addContact, approveAndSend, discardDraft, moveStatus, runTask, saveDraft, saveNotes, setDomain } from "../../actions";

export const dynamic = "force-dynamic";
const OPTIONS = STATUSES.map((s) => ({ value: s, label: statusLabel(s) }));
const TASK_LABEL: Record<string, string> = {
  prepare: "Prepare everything", tailor: "Tailor resume", find_contacts: "Find contacts", draft_outreach: "Draft emails",
  send_outreach: "Send email", autofill: "Open & autofill", prep: "Interview prep", cover_letter: "Cover letter",
  referral: "Referral message", discover: "Discovery",
};

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const j = await getJob(id);
  if (!j) notFound();
  const [resumes, contacts, outreach, docs, tasks] = await Promise.all([
    jobResumes(id), jobContacts(j.company, id), jobOutreach(id), jobDocuments(id), jobTasks(id),
  ]);
  const reasons = parseList(j.reasons);
  const gaps = parseList(j.missing_skills);
  const drafts = outreach.filter((o) => o.status === "draft");
  const others = outreach.filter((o) => o.status !== "draft");
  const pending = tasks.filter((t) => t.status === "queued" || t.status === "running");
  const linkedin = contacts.find((c) => c.linkedin_search_url)?.linkedin_search_url ??
    `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`"${j.company}" recruiter`)}`;
  const task = (kind: string, payload: object = {}) => runTask.bind(null, kind, id, payload);

  return (
    <>
      <Link href="/" className="text-sm text-ink-3 hover:text-ink">← Inbox</Link>
      <header className="mt-2 mb-4 flex flex-wrap items-start gap-4">
        <ScoreBadge score={Number(j.score)} method={j.method} />
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold tracking-tight">{j.title}</h1>
          <p className="mt-1 text-sm text-ink-2">
            {j.company} · {j.location || "—"}{j.remote ? " · Remote" : ""} · {sourceLabel(j.source)} · posted {timeAgo(j.posted_at || j.first_seen)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={j.status} />
          <StatusSelect action={moveStatus.bind(null, id)} value={j.status} options={OPTIONS} />
          <a href={j.url} target="_blank" rel="noreferrer" className={BTN.secondary}>Posting ↗</a>
        </div>
      </header>

      <div className="mb-5 flex flex-wrap gap-2">
        <ActionButton action={task("prepare")} variant="primary" pending="Queued…">Prepare everything</ActionButton>
        <ActionButton action={task("tailor")} pending="Queued…">Tailor resume</ActionButton>
        <ActionButton action={task("find_contacts")} pending="Queued…">Find contacts</ActionButton>
        <ActionButton action={task("draft_outreach")} pending="Queued…">Draft emails</ActionButton>
        <ActionButton action={task("autofill")} pending="Queued…" title="Opens a browser on your Mac, fills the form, never submits">Open & autofill on Mac</ActionButton>
        <ActionButton action={task("prep")} variant="ghost" pending="Queued…">Interview prep</ActionButton>
        <ActionButton action={task("cover_letter")} variant="ghost" pending="Queued…">Cover letter</ActionButton>
        <ActionButton action={task("referral")} variant="ghost" pending="Queued…">Referral message</ActionButton>
      </div>
      {pending.length > 0 && (
        <p className="mb-4 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-2" role="status">
          Working on: {pending.map((t) => TASK_LABEL[t.kind] ?? t.kind).join(", ")}. Your Mac worker picks these up within seconds; refresh to see results.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Why it fits" aside={<span className="text-xs text-ink-3">{j.method === "heuristic" ? "keyword score" : `scored by ${j.method}`}</span>} />
            <div className="space-y-2 px-4 py-3 text-sm">
              <ul className="list-disc space-y-1 pl-5 text-ink-2">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              {gaps.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 pt-1">
                  <span className="text-xs text-ink-3">Skills the JD mentions that you don&apos;t list:</span>
                  {gaps.map((g) => <Chip key={g} tone="gap">{g}</Chip>)}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title={`Email drafts${drafts.length ? ` (${drafts.length})` : ""}`}
              aside={<span className="text-xs text-ink-3">Nothing is sent until you approve</span>} />
            {drafts.length === 0 && <Empty>No drafts yet. Use “Draft emails” (find contacts first for a named recipient).</Empty>}
            <div className="divide-y divide-line">
              {drafts.map((d) => (
                <div key={d.id} className="px-4 py-3">
                  <DraftEditor draft={d} save={saveDraft.bind(null, d.id, id)} approve={approveAndSend.bind(null, d.id, id)}
                    discard={discardDraft.bind(null, d.id, id)} />
                </div>
              ))}
            </div>
            {others.length > 0 && (
              <ul className="divide-y divide-line border-t border-line text-sm">
                {others.map((o) => (
                  <li key={o.id} className="flex flex-wrap items-center gap-2 px-4 py-2">
                    <span className="font-medium">{o.subject}</span>
                    <span className="text-ink-3">→ {o.to_email}</span>
                    <span className="ml-auto text-xs text-ink-2">{o.status}{o.sent_at ? ` · ${timeAgo(o.sent_at)}` : ""}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {docs.length > 0 && (
            <Card>
              <CardHeader title="Documents" />
              <div className="divide-y divide-line">
                {docs.map((d) => (
                  <details key={d.id} className="group px-4 py-3" open={d.kind === "referral"}>
                    <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                      {d.title}<span className="text-xs font-normal text-ink-3">{timeAgo(d.created_at)}</span>
                      <span className="ml-auto"><CopyButton text={d.content} /></span>
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink-2">{d.content}</pre>
                  </details>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <details>
              <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">Job description</summary>
              <p className="whitespace-pre-wrap px-4 pb-4 text-sm leading-relaxed text-ink-2">{j.jd_text || "No description from this source; open the posting."}</p>
            </details>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Tailored resume" />
            {resumes.length === 0 ? <Empty>Not tailored yet.</Empty> : (
              <div className="space-y-2 px-4 py-3 text-sm">
                <a href={`/api/resume/${resumes[0].id}`} target="_blank" rel="noreferrer" className={BTN.secondary}>
                  Open PDF (v{resumes[0].version})
                </a>
                <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-ink-2">{resumes[0].diff_summary}</pre>
                {resumes.length > 1 && (
                  <p className="text-xs text-ink-3">Older: {resumes.slice(1).map((r) => (
                    <a key={r.id} href={`/api/resume/${r.id}`} target="_blank" rel="noreferrer" className="mr-2 underline">v{r.version}</a>))}
                  </p>
                )}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title="People to contact" aside={<a href={linkedin} target="_blank" rel="noreferrer" className="text-xs text-accent-ink hover:underline">Search LinkedIn ↗</a>} />
            {contacts.length === 0 ? <Empty>None yet. Find contacts, or add someone you found on LinkedIn.</Empty> : (
              <ul className="divide-y divide-line text-sm">
                {contacts.map((c) => (
                  <li key={c.id} className="px-4 py-2">
                    <p className="font-medium">{c.name || c.title || c.email}</p>
                    <p className="text-xs text-ink-2">{c.email} <span className="text-ink-3">· {c.source} · {c.confidence}%</span></p>
                  </li>
                ))}
              </ul>
            )}
            <form action={addContact.bind(null, id)} className="space-y-2 border-t border-line px-4 py-3">
              <p className="text-xs text-ink-2">Found someone on LinkedIn? Add them (email is guessed if blank):</p>
              <input name="name" placeholder="Full name" required className="w-full rounded-lg border border-line bg-surface px-3 py-1.5 text-sm" />
              <div className="flex gap-2">
                <input name="title" placeholder="Title" className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm" />
                <input name="email" placeholder="Email (optional)" className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm" />
              </div>
              <Submit pending="Queued…">Add contact</Submit>
            </form>
            <form action={setDomain.bind(null, id, j.company)} className="flex gap-2 border-t border-line px-4 py-3">
              <input name="domain" defaultValue={j.company_domain ?? ""} placeholder="company.com" aria-label="Company website domain"
                className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm" />
              <Submit pending="…">Set domain</Submit>
            </form>
          </Card>

          <Card>
            <CardHeader title="Notes" />
            <form action={saveNotes.bind(null, id)} className="space-y-2 px-4 py-3">
              <textarea name="notes" defaultValue={j.notes ?? ""} rows={4} placeholder="Referral from…, OA topics, recruiter name…"
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm" />
              <label className="flex items-center gap-2 text-xs text-ink-2">Deadline
                <input type="date" name="deadline" defaultValue={j.deadline?.slice(0, 10) ?? ""}
                  className="rounded-lg border border-line bg-surface px-2 py-1 text-sm" />
              </label>
              <Submit pending="Saving…">Save</Submit>
            </form>
          </Card>

          {tasks.length > 0 && (
            <Card>
              <CardHeader title="Recent tasks" />
              <ul className="divide-y divide-line text-xs">
                {tasks.slice(0, 8).map((t) => (
                  <li key={t.id} className="px-4 py-2">
                    <span className="font-medium">{TASK_LABEL[t.kind] ?? t.kind}</span>{" "}
                    <span className={t.status === "failed" ? "text-critical" : "text-ink-3"}>{t.status}</span>
                    <span className="text-ink-3"> · {timeAgo(t.created_at)}</span>
                    {t.error && <p className="mt-0.5 text-critical">{t.error}</p>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
