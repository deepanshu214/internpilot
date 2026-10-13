from datetime import datetime, timedelta, timezone

from worker import filters
from worker.config import SETTINGS
from worker.db import DB
from worker.match.score import heuristic_score
from worker.match.skills import find_skills, skill_gap
from worker.models import Job, clean_html


def job(title="Software Engineer Intern", location="Bengaluru, India", jd="", **kw):
    return Job(source="test", company="Acme", title=title, location=location, url="https://x", jd_text=jd, **kw)


def test_title_filter():
    assert filters.title_ok("Software Engineering Intern")
    assert filters.title_ok("Summer Internship - Backend")
    assert not filters.title_ok("Senior Software Engineer")
    assert not filters.title_ok("Software Engineer")
    assert not filters.title_ok("PhD Research Intern")
    assert not filters.title_ok("Internal Tools Engineer")
    assert filters.title_ok("Security Engineering Intern (Summer 2027)")


def test_location_and_freshness():
    assert filters.keep(job())
    assert not filters.keep(job(location="San Francisco, CA"))
    assert filters.keep(job(location="Remote", remote=True))
    assert not filters.keep(job(location="Remote in USA", remote=True))
    assert not filters.keep(job(location="San Francisco, CA; Remote in USA"))
    old = datetime.now(timezone.utc) - timedelta(days=SETTINGS["max_age_days"] + 5)
    assert not filters.keep(job(posted_at=old))


def test_dedup_id_normalizes():
    assert job(title="SWE Intern ").id == job(title="swe intern").id
    assert job(title="SWE Intern").id != job(title="ML Intern").id


def test_skill_matching_boundaries():
    assert find_skills("Experience with C++ and Postgres", ["C++", "PostgreSQL"]) == {"C++", "PostgreSQL"}
    assert find_skills("javascript developer", ["Java"]) == set()
    have, missing = skill_gap("We use Python, FastAPI, Kubernetes and Kafka. Go above and beyond!")
    assert {"Python", "FastAPI"} <= set(have)
    assert {"Kubernetes", "Kafka"} <= set(missing)
    assert "Go" not in missing


def test_heuristic_prefers_relevant_jd():
    good = job(jd="Backend intern: Python, FastAPI, PostgreSQL, Docker, REST APIs, network security, JWT. " * 5)
    bad = job(jd="iOS intern: Swift, Kotlin, Android, React, Angular, Ruby, PHP mobile apps. " * 5)
    assert heuristic_score(good, 0.5)[0] > heuristic_score(bad, 0.5)[0]


def test_clean_html():
    assert clean_html("&lt;p&gt;Hello &amp;amp; world&lt;/p&gt;") == "Hello & world"


def test_db_roundtrip(tmp_path):
    db = DB(url="", sqlite_path=str(tmp_path / "t.db"))
    j = job()
    db.insert_job(j, None)
    db.insert_job(j, None)  # idempotent
    db.upsert_match(j.id, 90, ["r"], ["Kafka"], "heuristic")
    assert db.existing_ids([j.id, "nope"]) == {j.id}
    rows = db.pending_alerts(70, 10)
    assert len(rows) == 1 and rows[0]["score"] == 90
    db.mark_notified([j.id])
    assert db.pending_alerts(70, 10) == []
