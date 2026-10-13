import pytest

from worker import agent, docs, llm
from worker.db import DB
from worker.models import Job
from worker.notify import telegram


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: None)
    monkeypatch.setattr(telegram, "send", lambda *a, **k: True)
    monkeypatch.setattr(docs, "find_domain", lambda *a: None)
    monkeypatch.setattr(docs, "company_brief", lambda *a: "Acme builds payment APIs")
    d = DB(url="", sqlite_path=str(tmp_path / "t.db"))
    j = Job(source="t", company="Acme", title="Backend Intern", location="India", url="https://x",
            jd_text="Python, FastAPI, PostgreSQL, Kafka, Docker. Build REST APIs.")
    d.insert_job(j, None)
    d.upsert_match(j.id, 80, [], ["Kafka"], "heuristic")
    d.job_id = j.id
    return d


def test_prep_pack_and_cover_letter(db):
    prep = db.get("documents", docs.prep_pack(db, db.job_id))["content"]
    assert "## Likely technical questions" in prep and "Kafka" in prep and "MoodSpace" in prep
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
