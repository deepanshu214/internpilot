"""Copy everything from the local SQLite database into Supabase (run once after setting DATABASE_URL in .env).
Existing rows in Supabase are kept (on conflict do nothing), so it's safe to run twice."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.config import DATABASE_URL, SQLITE_PATH  # noqa: E402
from worker.db import DB, schema_columns  # noqa: E402

KEYS = {"matches": "job_id", "kv": "key", "companies": "name"}
ORDER = ["jobs", "matches", "resumes", "contacts", "outreach", "tasks", "documents", "companies", "kv", "events"]


def copy(source_path: str, target: DB) -> dict:
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row
    counts = {}
    for table in ORDER:
        cols = [c for c, _ in schema_columns()[table]]
        have = {r[1] for r in src.execute(f"pragma table_info({table})")}
        cols = [c for c in cols if c in have]
        rows = src.execute(f"select {', '.join(cols)} from {table}").fetchall()
        sql = (f"insert into {table} ({', '.join(cols)}) values ({', '.join('?' * len(cols))})"
               f" on conflict ({KEYS.get(table, 'id')}) do nothing")
        for r in rows:
            target.execute(sql, tuple(r))
        counts[table] = len(rows)
    return counts


if __name__ == "__main__":
    if not DATABASE_URL:
        sys.exit("Set DATABASE_URL in .env to your Supabase connection string first.")
    print(copy(SQLITE_PATH, DB()))
