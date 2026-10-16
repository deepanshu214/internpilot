"""Tiny DB layer: Supabase Postgres when DATABASE_URL is set, local SQLite otherwise.
SQL is written with `?` placeholders and portable types so both backends run the same statements.
(Don't put a literal `?` or `%` in SQL text; pass values as params.)"""
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from .config import DATABASE_URL, ROOT, SQLITE_PATH

SCHEMA = (ROOT / "supabase/migrations/001_init.sql").read_text()
PG_ONLY = (ROOT / "supabase/migrations/postgres_only.sql").read_text()
_TABLE = re.compile(r"create table if not exists (\w+) \((.*?)\n\);", re.S)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


def schema_columns(schema: str = SCHEMA) -> dict[str, list[tuple[str, str]]]:
    """{table: [(column, add-column type clause)]} parsed from the migration file."""
    tables = {}
    for name, body in _TABLE.findall(schema):
        cols = []
        for line in body.splitlines():
            line = re.sub(r"--.*", "", line).strip().rstrip(",")
            if not line:
                continue
            col, rest = line.split(None, 1)
            default = re.search(r"default\s+('[^']*'|\S+)", rest)
            cols.append((col, rest.split()[0] + (f" default {default.group(1)}" if default else "")))
        tables[name] = cols
    return tables


class DB:
    def __init__(self, url: str = DATABASE_URL, sqlite_path: str = SQLITE_PATH):
        self.url, self.sqlite_path, self.pg = url, sqlite_path, bool(url)
        self._connect()
        self.migrate()

    def _connect(self):
        if self.pg:
            import psycopg
            # prepare_threshold=None: Supabase's transaction pooler doesn't support prepared statements.
            self.conn = psycopg.connect(self.url, autocommit=True, prepare_threshold=None)
        else:
            self.conn = sqlite3.connect(self.sqlite_path, timeout=30)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("pragma journal_mode=wal")  # dashboard reads while the worker writes

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def _reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self._connect()

    def execute(self, sql: str, params=()):
        if self.pg and (self.conn.closed or self.conn.broken):
            self._reconnect()  # an earlier reconnect failed (still offline): try again now
        try:
            cur = self.conn.cursor()
            cur.execute(self._sql(sql), params)
        except Exception as e:
            # Long-running worker: Supabase drops idle connections, and the Mac sleeps or switches networks.
            # After any connection-level error psycopg's connection is unusable ("another command is already
            # in progress"), so open a fresh one and retry once.
            import psycopg
            if not self.pg or not isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError)):
                raise
            self._reconnect()
            cur = self.conn.cursor()
            cur.execute(self._sql(sql), params)
        if not self.pg:
            self.conn.commit()
        return cur

    def query(self, sql: str, params=()) -> list[dict]:
        cur = self.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def migrate(self):
        for stmt in filter(str.strip, SCHEMA.split(";")):
            self.execute(stmt)
        if self.pg:
            for stmt in filter(str.strip, PG_ONLY.split(";")):
                self.execute(stmt)
        # Add columns introduced after a table was first created.
        for table, cols in schema_columns().items():
            if self.pg:
                have = {r["column_name"] for r in self.query(
                    "select column_name from information_schema.columns where table_name = ?", (table,))}
            else:
                have = {r["name"] for r in self.query(f"pragma table_info({table})")}
            for col, typ in cols:
                if col not in have:
                    self.execute(f"alter table {table} add column {col} {typ}")

    # --- generic helpers ---------------------------------------------------
    def insert(self, table: str, row: dict) -> dict:
        row = dict(row)
        if "id" in dict(schema_columns()[table]) and not row.get("id"):
            row["id"] = new_id()
        cols = list(row)
        self.execute(f"insert into {table} ({', '.join(cols)}) values ({', '.join('?' * len(cols))})",
                     [_db_value(row[c]) for c in cols])
        return row

    def update(self, table: str, key_value, fields: dict, key: str = "id"):
        if not fields:
            return
        sets = ", ".join(f"{c} = ?" for c in fields)
        self.execute(f"update {table} set {sets} where {key} = ?", [*map(_db_value, fields.values()), key_value])

    def get(self, table: str, key_value, key: str = "id") -> dict | None:
        return self.one(f"select * from {table} where {key} = ?", (key_value,))

    def kv_get(self, key: str, default=None):
        row = self.get("kv", key, key="key")
        return json.loads(row["value"]) if row else default

    def kv_set(self, key: str, value):
        self.execute("insert into kv (key, value) values (?, ?) on conflict (key) do update set value = excluded.value",
                     (key, json.dumps(value)))

    # --- jobs -------------------------------------------------------------
    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        found = set()
        for i in range(0, len(ids), 500):  # SQLite caps bound parameters
            chunk = ids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            found |= {r["id"] for r in self.query(f"select id from jobs where id in ({marks})", chunk)}
        return found

    def insert_job(self, job, embedding):
        self.execute(
            "insert into jobs (id, source, company, title, location, remote, url, jd_text, posted_at, first_seen,"
            " embedding, extra) values (?,?,?,?,?,?,?,?,?,?,?,?) on conflict (id) do nothing",
            (job.id, job.source, job.company, job.title, job.location, int(job.remote), job.url, job.jd_text,
             job.posted_at.isoformat() if job.posted_at else None, now(),
             json.dumps(embedding) if embedding else None, json.dumps(job.extra) if job.extra else None),
        )

    def job_with_match(self, job_id: str) -> dict | None:
        return self.one("select j.*, m.score, m.reasons, m.missing_skills, m.status, m.deadline from jobs j"
                        " left join matches m on m.job_id = j.id where j.id = ?", (job_id,))

    # --- matches ----------------------------------------------------------
    def upsert_match(self, job_id, score, reasons, missing, method, deadline=None):
        self.execute(
            "insert into matches (job_id, score, reasons, missing_skills, method, status, notified, deadline, updated_at)"
            " values (?,?,?,?,?, 'new', 0, ?, ?) on conflict (job_id) do update set score=excluded.score,"
            " reasons=excluded.reasons, missing_skills=excluded.missing_skills, method=excluded.method,"
            " updated_at=excluded.updated_at",
            (job_id, score, json.dumps(reasons), json.dumps(missing), method, deadline, now()),
        )

    def set_status(self, job_id: str, status: str, **extra):
        self.update("matches", job_id, {"status": status, "updated_at": now(), **extra}, key="job_id")
        self.log("status", status, job_id)

    def pending_alerts(self, threshold: int, limit: int) -> list[dict]:
        return self.query(
            "select j.*, m.score, m.reasons, m.missing_skills, m.method from matches m join jobs j on j.id = m.job_id"
            " where m.notified = 0 and m.score >= ? and m.status = 'new' order by m.score desc limit ?",
            (threshold, limit),
        )

    def mark_notified(self, job_ids):
        for jid in job_ids:
            self.execute("update matches set notified = 1 where job_id = ?", (jid,))

    # --- tasks ------------------------------------------------------------
    def enqueue(self, kind: str, job_id: str | None = None, payload: dict | None = None) -> str:
        # Microsecond timestamps: tasks queued in the same second must still run in order
        # (prepare → tailor → find_contacts → draft_outreach).
        row = self.insert("tasks", {"kind": kind, "job_id": job_id, "payload": payload or {}, "status": "queued",
                                    "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")})
        return row["id"]

    def next_task(self) -> dict | None:
        task = self.one("select * from tasks where status = 'queued' order by created_at limit 1")
        if task:
            self.update("tasks", task["id"], {"status": "running", "started_at": now()})
            task["payload"] = json.loads(task["payload"] or "{}")
        return task

    def log(self, kind: str, detail: str, job_id: str | None = None):
        self.execute("insert into events (id, ts, kind, job_id, detail) values (?,?,?,?,?)",
                     (new_id(), now(), kind, job_id, detail))


def _db_value(v):
    return json.dumps(v) if isinstance(v, (dict, list)) else v
