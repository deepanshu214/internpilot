import base64
from datetime import datetime

import pytest

from worker import gmail, llm
from worker.db import DB, now
from worker.models import Job
from worker.notify import digest, telegram
from worker.sources.gmail_alerts import parse_alert
from worker.tracking import inbox


def msg(subject, text, sender="no-reply@greenhouse.io", thread="t1", mid="m1"):
    return {"id": mid, "threadId": thread, "from": sender, "to": "me", "subject": subject, "date": None,
            "message_id": "<x>", "snippet": text[:100], "text": text, "html": ""}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text, buttons=None: sent.append(text) or True)
    return sent


@pytest.fixture
def db(tmp_path):
    d = DB(url="", sqlite_path=str(tmp_path / "t.db"))
    for company, title, status in [("Razorpay", "Backend Intern", "tailored"), ("Acme", "Security Intern", "applied"),
                                   ("Razorpay", "Data Intern", "new")]:
        j = Job(source="t", company=company, title=title, location="India", url=f"https://x/{title}")
        d.insert_job(j, None)
        d.upsert_match(j.id, 80, [], [], "heuristic")
        if status != "new":
            d.set_status(j.id, status)
    return d


@pytest.mark.parametrize("subject,text,kind", [
    ("Thank you for applying to Razorpay", "We have received your application for Backend Intern.", "applied"),
    ("Razorpay | Online Assessment", "Please complete the HackerRank coding test by October 20.", "oa"),
    ("Interview invitation", "We'd like to schedule an interview with you for the next round.", "interview"),
    ("Your application", "Unfortunately, we have decided to move forward with other candidates.", "rejection"),
    ("Offer", "We are pleased to offer you the Summer Internship.", "offer"),
    ("Weekly newsletter", "Here are this week's top stories.", "other"),
])
def test_classify(subject, text, kind):
    assert inbox.classify(msg(subject, text)) == kind


def test_find_deadline():
    ref = datetime(2026, 10, 14)
    assert inbox.find_deadline("Please complete by October 20.", ref) == "2026-10-20"
    assert inbox.find_deadline("deadline: 3 Nov", ref) == "2026-11-03"
    assert inbox.find_deadline("submit within 72 hours", ref) == "2026-10-17"
    assert inbox.find_deadline("by Jan 5", ref) == "2027-01-05"
    assert inbox.find_deadline("no dates here", ref) is None


def test_match_job_ignores_unshortlisted_and_prefers_title(db):
    m = inbox.match_job(db, msg("Razorpay: Backend Intern update", "Hi from Razorpay"))
    assert m["title"] == "Backend Intern"
    assert inbox.match_job(db, msg("Hello", "Nothing about any company")) is None


def test_status_never_moves_backwards(db):
    acme = inbox.match_job(db, msg("Acme", "Acme team"))
    assert inbox.apply_update(db, acme, "oa", msg("Acme OA", "complete by Oct 30")) == "oa"
    acme = inbox.match_job(db, msg("Acme", "Acme team"))
    assert inbox.apply_update(db, acme, "applied", msg("Acme", "thanks for applying")) is None
    m = db.get("matches", acme["id"], key="job_id")
    assert m["status"] == "oa" and m["deadline"].endswith("-10-30")
    assert inbox.apply_update(db, acme, "rejection", msg("Acme", "unfortunately")) == "rejected"
    acme = inbox.match_job(db, msg("Acme", "Acme team"))
    assert inbox.apply_update(db, acme, "interview", msg("Acme", "interview")) is None


def test_inbox_run_with_fake_gmail(db, monkeypatch, quiet):
    o = db.insert("outreach", {"kind": "cold", "status": "sent", "gmail_thread_id": "thread-cold", "subject": "s",
                               "body": "b", "to_email": "p@x.dev", "sent_at": now()})
    mails = {"a": msg("Thank you for applying to Razorpay", "Backend Intern application received", mid="a", thread="t-a"),
             "b": msg("Re: NetGuard", "Happy to chat!", sender="priya@acme.dev", mid="b", thread="thread-cold")}
    monkeypatch.setattr(gmail, "available", lambda: True)
    monkeypatch.setattr(gmail, "search", lambda q, n=100: list(mails))
    monkeypatch.setattr(gmail, "get", lambda mid: mails[mid])
    out = inbox.run(db)
    assert out["checked"] == 2
    assert db.get("outreach", o["id"])["status"] == "replied"
    statuses = {r["title"]: r["status"] for r in db.query(
        "select j.title, m.status from jobs j join matches m on m.job_id = j.id")}
    assert statuses["Backend Intern"] == "applied"
    assert any("Reply to your cold email" in t for t in quiet)
    assert inbox.run(db)["checked"] == 0               # already-seen messages are skipped


def test_parse_message_decodes_parts():
    enc = lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
    m = {"id": "1", "threadId": "t", "snippet": "hi", "payload": {
        "headers": [{"name": "From", "value": "A <a@x.com>"}, {"name": "Subject", "value": "Hello"},
                    {"name": "Date", "value": "Tue, 13 Oct 2026 10:00:00 +0530"}],
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": "text/plain", "body": {"data": enc("plain body")}},
                  {"mimeType": "text/html", "body": {"data": enc("<p>html body</p>")}}]}}
    p = gmail.parse_message(m)
    assert p["subject"] == "Hello" and p["text"] == "plain body" and "html body" in p["html"]
    assert p["date"].startswith("2026-10-13")


def test_parse_linkedin_alert():
    html = """<table><tr><td>
      <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc&refId=x">Software Engineer Intern</a>
      <p>Razorpay · Bengaluru, Karnataka, India</p><a href="https://www.linkedin.com/comm/jobs/view/4012345678/">View job</a>
    </td></tr><tr><td>
      <a href="https://www.linkedin.com/comm/jobs/view/4099999999/?x=1">Security Analyst Intern</a>
      <p>CRED</p><p>Bengaluru, India (Hybrid)</p></td></tr>
      <a href="https://www.linkedin.com/comm/jobs/search">See all jobs</a></table>"""
    jobs = parse_alert("linkedin", html)
    assert [(j.title, j.company) for j in jobs] == [("Software Engineer Intern", "Razorpay"),
                                                    ("Security Analyst Intern", "CRED")]
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/4012345678"
    assert "India" in jobs[1].location


def test_digest_once_per_day_and_weekly(db, quiet):
    sunday_night = datetime(2026, 10, 18, 21, 30)
    assert digest.maybe_send(db, sunday_night) == ["daily", "weekly"]
    assert digest.maybe_send(db, sunday_night) == []
    assert "Daily digest" in quiet[0] and "Weekly review" in quiet[1]
    assert db.one("select count(*) n from documents where kind = 'weekly_report'")["n"] == 1
    assert digest.maybe_send(db, datetime(2026, 10, 19, 9, 0)) == []   # before 21:00
