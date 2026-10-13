import { one, query } from "./db";

export const STATUSES = ["new", "shortlisted", "tailored", "applied", "oa", "interview", "offer", "rejected", "skipped"] as const;
export type Status = (typeof STATUSES)[number];

export type JobRow = {
  id: string; source: string; company: string; title: string; location: string | null; remote: number;
  url: string; jd_text: string | null; posted_at: string | null; first_seen: string; company_domain: string | null;
  extra: string | null; score: number; reasons: string | null; missing_skills: string | null; method: string | null;
  status: Status; notes: string | null; applied_at: string | null; deadline: string | null; updated_at: string | null;
};
export type Outreach = {
  id: string; contact_id: string | null; job_id: string | null; kind: string; parent_id: string | null;
  variant: string | null; project_pitched: string | null; subject: string; body: string; to_email: string | null;
  resume_id: string | null; status: string; sent_at: string | null; followup_due: string | null;
  created_at: string | null; updated_at: string | null; company?: string; title?: string;
};
export type Contact = { id: string; company: string; domain: string | null; name: string | null; title: string | null;
  email: string | null; source: string | null; confidence: number | null; linkedin_search_url: string | null };
export type Task = { id: string; kind: string; job_id: string | null; status: string; error: string | null;
  result: string | null; created_at: string; finished_at: string | null; title?: string; company?: string };

export const parseList = (s: string | null | undefined): string[] => {
  try {
    const v = JSON.parse(s || "[]");
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
};

const JOB_COLS = `j.id, j.source, j.company, j.title, j.location, j.remote, j.url, j.posted_at, j.first_seen,
  j.company_domain, j.extra, m.score, m.reasons, m.missing_skills, m.method, m.status, m.notes, m.applied_at,
  m.deadline, m.updated_at`;

export async function inbox(opts: { minScore: number; source?: string; q?: string; limit?: number }) {
  const where = ["m.status = 'new'", "m.score >= ?"];
  const params: (string | number)[] = [opts.minScore];
  if (opts.source) {
    where.push("j.source like ?");
    params.push(`${opts.source}%`);
  }
  if (opts.q) {
    where.push("(lower(j.title) like ? or lower(j.company) like ?)");
    params.push(`%${opts.q.toLowerCase()}%`, `%${opts.q.toLowerCase()}%`);
  }
  params.push(opts.limit ?? 60);
  return query<JobRow>(`select ${JOB_COLS} from matches m join jobs j on j.id = m.job_id where ${where.join(" and ")}
    order by m.score desc, j.first_seen desc limit ?`, params);
}

export async function sources() {
  return query<{ source: string; n: number }>(
    "select j.source, count(*) as n from jobs j join matches m on m.job_id = j.id where m.status = 'new' group by j.source order by n desc");
}

export async function pipeline() {
  return query<JobRow>(`select ${JOB_COLS} from matches m join jobs j on j.id = m.job_id
    where m.status not in ('new', 'skipped') order by m.updated_at desc limit 300`);
}

export async function job(id: string) {
  return one<JobRow>(`select ${JOB_COLS}, j.jd_text from matches m join jobs j on j.id = m.job_id where j.id = ?`, [id]);
}

export async function jobResumes(id: string) {
  return query<{ id: string; version: number; diff_summary: string; created_at: string; keywords: string }>(
    "select id, version, diff_summary, created_at, keywords from resumes where job_id = ? order by version desc", [id]);
}

export async function jobContacts(company: string, id: string) {
  return query<Contact>("select * from contacts where job_id = ? or company = ? order by confidence desc", [id, company]);
}

export async function jobOutreach(id: string) {
  return query<Outreach>("select * from outreach where job_id = ? order by created_at desc", [id]);
}

export async function jobDocuments(id: string) {
  return query<{ id: string; kind: string; title: string; content: string; created_at: string }>(
    "select * from documents where job_id = ? order by created_at desc", [id]);
}

export async function jobTasks(id: string) {
  return query<Task>("select * from tasks where job_id = ? order by created_at desc limit 20", [id]);
}

export async function outreachList(status?: string) {
  const params: string[] = [];
  let where = "";
  if (status && status !== "all") {
    where = "where o.status = ?";
    params.push(status);
  }
  return query<Outreach>(`select o.*, j.company, j.title from outreach o left join jobs j on j.id = o.job_id ${where}
    order by coalesce(o.sent_at, o.created_at) desc limit 200`, params);
}

export async function counts() {
  const rows = await query<{ status: string; n: number }>("select status, count(*) n from matches group by status");
  const by: Record<string, number> = Object.fromEntries(rows.map((r) => [r.status, Number(r.n)]));
  const o = await query<{ status: string; n: number }>("select status, count(*) n from outreach group by status");
  const ob: Record<string, number> = Object.fromEntries(o.map((r) => [r.status, Number(r.n)]));
  return { matches: by, outreach: ob };
}

export async function workerStatus() {
  const hb = await one<{ value: string }>("select value from kv where key = 'worker_heartbeat'");
  const last = await one<{ value: string }>("select value from kv where key = 'last_discover'");
  const queued = await one<{ n: number }>("select count(*) n from tasks where status in ('queued', 'running')");
  const beat = hb ? JSON.parse(hb.value) as string : null;
  const ageSec = beat ? (Date.now() - Date.parse(beat)) / 1000 : Infinity;
  const lastRun = await one<{ ts: string; detail: string }>("select ts, detail from events where kind = 'run' order by ts desc limit 1");
  return { online: ageSec < 120, heartbeat: beat, queued: Number(queued?.n ?? 0), lastRun, lastDiscover: last?.value };
}

export async function recentTasks() {
  return query<Task>(`select t.*, j.title, j.company from tasks t left join jobs j on j.id = t.job_id
    order by t.created_at desc limit 40`);
}

export async function recentEvents() {
  return query<{ id: string; ts: string; kind: string; job_id: string | null; detail: string; title: string | null }>(
    `select e.*, j.title from events e left join jobs j on j.id = e.job_id order by e.ts desc limit 80`);
}
