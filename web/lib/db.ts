// Same database the worker uses: Supabase Postgres when DATABASE_URL is set (Vercel), else the local
// SQLite file next to the worker (../internpilot.db). SQL uses `?` placeholders for both backends.
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import postgres from "postgres";

export type Row = Record<string, unknown>;

const g = globalThis as unknown as { __ipSqlite?: DatabaseSync; __ipPg?: ReturnType<typeof postgres> };

function pg() {
  // prepare: false → works with Supabase's transaction pooler (port 6543)
  g.__ipPg ??= postgres(process.env.DATABASE_URL!, { prepare: false, max: 3, idle_timeout: 20 });
  return g.__ipPg;
}

function sqlite() {
  if (!g.__ipSqlite) {
    const file = process.env.SQLITE_PATH || path.join(process.cwd(), "..", "internpilot.db");
    g.__ipSqlite = new DatabaseSync(file);
    g.__ipSqlite.exec("pragma busy_timeout = 5000");
  }
  return g.__ipSqlite;
}

const toPg = (sql: string) => {
  let i = 0;
  return sql.replace(/\?/g, () => `$${++i}`);
};

type Param = string | number | null;

export async function query<T = Row>(sql: string, params: Param[] = []): Promise<T[]> {
  if (process.env.DATABASE_URL) return (await pg().unsafe(toPg(sql), params)) as unknown as T[];
  return sqlite().prepare(sql).all(...params).map((r) => ({ ...r })) as T[];
}

export async function one<T = Row>(sql: string, params: Param[] = []): Promise<T | undefined> {
  return (await query<T>(sql, params))[0];
}

export async function run(sql: string, params: Param[] = []): Promise<void> {
  if (process.env.DATABASE_URL) {
    await pg().unsafe(toPg(sql), params);
    return;
  }
  sqlite().prepare(sql).run(...params);
}

/** ISO-8601 UTC with seconds, matching the Python worker's timestamps. */
export const now = () => new Date().toISOString().slice(0, 19) + "+00:00";
export const newId = () => crypto.randomUUID().replaceAll("-", "");

export async function enqueue(kind: string, jobId: string | null, payload: object = {}) {
  const id = newId();
  await run("insert into tasks (id, kind, job_id, payload, status, created_at) values (?, ?, ?, ?, 'queued', ?)", [
    id, kind, jobId, JSON.stringify(payload), now(),
  ]);
  return id;
}

export async function logEvent(kind: string, detail: string, jobId: string | null = null) {
  await run("insert into events (id, ts, kind, job_id, detail) values (?, ?, ?, ?, ?)", [newId(), now(), kind, jobId, detail]);
}
