import pytest

from worker import agent, docs, llm
from worker.db import DB
from worker.models import Job
from worker.notify import telegram


@pytest.fixture
def db(tmp_path, monkeypatch, make_db):
    monkeypatch.setattr(llm, "available", lambda *a, **k: None)
    monkeypatch.setattr(telegram, "send", lambda *a, **k: True)
    monkeypatch.setattr(docs, "find_domain", lambda *a: None)
    monkeypatch.setattr(docs, "company_brief", lambda *a: "Acme builds payment APIs")
    d = make_db()
    j = Job(source="t", company="Acme", title="Backend Intern", location="India", url="https://x",
            jd_text="Python, FastAPI, PostgreSQL, Kafka, Docker. Build REST APIs.")
    d.insert_job(j, None)
    d.upsert_match(j.id, 80, [], ["Kafka"], "heuristic")
    d.job_id = j.id
    return d


def test_prep_pack_and_cover_letter(db):
    prep = db.get("documents", docs.prep_pack(db, db.job_id))["content"]
    from worker.config import PROFILE
    assert "## Likely technical questions" in prep and "Kafka" in prep
    assert any(p["name"] in prep for p in PROFILE["projects"] if p.get("outreach", True))  # talking points: a real project
    letter = db.get("documents", docs.cover_letter(db, db.job_id))["content"]
    assert letter.startswith("Dear Acme Hiring Team") and "Kafka" not in letter


def test_agent_tick_runs_queue_and_is_rate_limited(db, monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "run_once", lambda d: calls.append("discover") or {})
    monkeypatch.setattr(agent.gmail, "available", lambda: False)
    db.enqueue("prep", db.job_id)
    agent.tick(db)
    agent.tick(db)
    assert calls == ["discover"]                       # second tick: not due yet
    assert db.one("select status from tasks")["status"] == "done"
    assert db.kv_get("worker_heartbeat")


def test_offline_errors_are_recognised():
    import requests
    from worker.agent import offline
    try:
        try:
            raise OSError("[Errno 8] nodename nor servname provided, or not known")
        except OSError as inner:
            raise requests.ConnectionError("Max retries exceeded") from inner
    except requests.ConnectionError as e:
        assert offline(e)
    assert not offline(ValueError("bad data"))
    import psycopg
    assert offline(psycopg.OperationalError("consuming input failed: could not receive data from server: Operation timed out"))


def test_db_reconnects_after_network_drop():
    """After the Mac sleeps, psycopg's connection is wedged ("another command is already in progress");
    the worker must open a fresh one instead of failing every tick forever."""
    import psycopg

    class Conn:
        def __init__(self, fail):
            self.fail, self.closed, self.broken = fail, False, False

        def cursor(self):
            conn = self

            class Cur:
                def execute(self, sql, params):
                    if conn.fail:
                        raise psycopg.OperationalError("another command is already in progress")
            return Cur()

        def close(self):
            self.closed = True

    db = DB.__new__(DB)
    db.pg, db.conn = True, Conn(fail=True)
    wedged, fresh = db.conn, []
    db._connect = lambda: (fresh.append(Conn(fail=False)), setattr(db, "conn", fresh[-1]))
    db.execute("select 1")
    assert wedged.closed and db.conn is fresh[0]

    # Reconnect itself failed (still offline): the next call tries again instead of reusing the dead connection.
    db.conn.closed = True
    db.execute("select 1")
    assert len(fresh) == 2

    # Ordinary SQL errors are not retried.
    class Bad(Conn):
        def cursor(self):
            class Cur:
                def execute(self, sql, params):
                    raise psycopg.errors.SyntaxError("bad sql")
            return Cur()
    db.conn = Bad(fail=False)
    try:
        db.execute("selec 1")
        raise AssertionError("expected a SyntaxError")
    except psycopg.errors.SyntaxError:
        pass
    assert len(fresh) == 2
