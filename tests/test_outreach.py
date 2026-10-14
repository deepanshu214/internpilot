import email
from datetime import datetime, timedelta, timezone

import pytest

from worker import llm, tasks
from worker.db import DB, now
from worker.models import Job
from worker.notify import telegram, telegram_bot
from worker.outreach import company, draft, followup, send
from worker.outreach.contacts import guess_emails, linkedin_search_url


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "available", lambda *a, **k: None)
    monkeypatch.setattr(company, "find_domain", lambda db, c, u="": "acme.dev")
    monkeypatch.setattr(draft, "find_domain", lambda db, c, u="": "acme.dev")
    monkeypatch.setattr(draft, "company_brief", lambda db, c, d: "Acme builds network observability tools for SREs")
    monkeypatch.setattr("worker.config.OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr("worker.gmail.OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.setattr("worker.tailor.service.OUTPUT_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text, buttons=None: sent.append(text) or True)
    return sent


@pytest.fixture
def db(tmp_path, make_db):
    d = make_db()
    job = Job(source="greenhouse", company="Acme Pvt. Ltd.", title="Security Engineering Intern (Summer 2027)",
              location="Bengaluru, India", url="https://boards.greenhouse.io/acme/jobs/1",
              jd_text="Work on intrusion detection and network security in Python. Linux, Wireshark, firewalls.")
    d.insert_job(job, None)
    d.upsert_match(job.id, 88, ["fit"], [], "heuristic")
    d.job_id = job.id
    d.contact = d.insert("contacts", {"company": "Acme Pvt. Ltd.", "job_id": job.id, "name": "Priya Sharma",
                                      "title": "Talent Acquisition", "email": "priya@acme.dev", "source": "manual",
                                      "confidence": 90, "created_at": now()})
    return d


def test_guess_emails_and_links():
    assert guess_emails("Priya", "Sharma", "acme.dev")[:2] == ["priya.sharma@acme.dev", "priya@acme.dev"]
    assert "linkedin.com/search/results/people" in linkedin_search_url("Acme")


def test_candidate_domains_skip_job_boards():
    c = company.candidate_domains("Acme Technologies Pvt Ltd", "https://boards.greenhouse.io/acme/jobs/1")
    assert "acme.com" in c and not any("greenhouse" in d for d in c)
    assert company.candidate_domains("Foo", "https://careers.foo.io/jobs/1")[0] == "foo.io"


def test_template_draft_is_specific_and_honest(db):
    out = draft.draft_outreach(db, db.job_id)
    o = db.get("outreach", out["drafts"][0])
    assert o["status"] == "draft" and o["to_email"] == "priya@acme.dev"
    assert o["body"].startswith("Hi Priya,")
    assert "Acme" in o["body"] and "Pvt" not in o["body"]
    assert "NetGuard" in o["body"]                 # security role → security project
    assert "github.com/deepanshu214/NetGuard" in o["body"]
    lo, hi = 90, 150
    body_words = len(o["body"].split("Best,")[0].split())
    assert lo - 15 <= body_words <= hi + 25
    # second call doesn't duplicate the draft for the same contact
    assert draft.draft_outreach(db, db.job_id)["drafts"] == []


def test_llm_email_with_invented_skill_falls_back_to_template(db, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda *a, **k: "groq_large")
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {
        "subject": "Kubernetes expert here", "body": "Hi Priya, I have 3 years of Kubernetes and Rust experience at Acme. " * 6})
    out = draft.draft_outreach(db, db.job_id)
    body = db.get("outreach", out["drafts"][0])["body"]
    assert "Kubernetes" not in body and "Rust" not in body


def test_check_email_rules():
    f = {"company": "Acme", "project": {"name": "NetGuard"}}
    ok_body = ("Hi Priya, Acme builds tools. " + "I built NetGuard with Python. " * 12).strip()
    assert draft.check_email("Hello", ok_body, f, 60, 150) is None
    assert "placeholder" in draft.check_email("Hi [Name]", ok_body, f, 60, 150)
    assert "skills" in draft.check_email("x", ok_body + " Also Kubernetes.", f, 60, 150)
    assert "numbers" in draft.check_email("x", ok_body + " Improved latency 73%.", f, 60, 150)


def test_send_requires_approval_and_writes_eml_in_dry_run(db, tmp_path):
    oid = draft.draft_outreach(db, db.job_id)["drafts"][0]
    with pytest.raises(send.NotAllowed):
        send.send_outreach(db, oid, dry_run=True)       # still a draft
    db.update("outreach", oid, {"status": "approved"})
    res = send.send_outreach(db, oid, dry_run=True)
    assert res["dry_run"] and res["path"].endswith(".eml")
    msg = email.message_from_bytes(open(res["path"], "rb").read())
    assert msg["To"] == "priya@acme.dev"
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["Deepanshu_Agarwal_Resume.pdf"]    # tailored resume attached (tailored on demand)
    o = db.get("outreach", oid)
    assert o["status"] == "sent" and o["followup_due"]
    with pytest.raises(send.NotAllowed):
        send.send_outreach(db, oid, dry_run=True)       # already sent


def test_daily_cap(db, monkeypatch):
    monkeypatch.setitem(send.SETTINGS["outreach"], "daily_cap", 1)
    a = db.insert("outreach", {"job_id": db.job_id, "kind": "cold", "status": "sent", "to_email": "a@x.dev",
                               "subject": "s", "body": "b", "sent_at": now()})
    b = db.insert("outreach", {"job_id": db.job_id, "kind": "cold", "status": "approved", "to_email": "b@x.dev",
                               "subject": "s", "body": "b"})
    assert a
    with pytest.raises(send.NotAllowed, match="daily cap"):
        send.send_outreach(db, b["id"], dry_run=True)


def test_real_send_needs_gmail(db, monkeypatch):
    monkeypatch.setattr("worker.gmail.available", lambda: False)
    o = db.insert("outreach", {"job_id": db.job_id, "kind": "cold", "status": "approved", "to_email": "b@x.dev",
                               "subject": "s", "body": "b"})
    with pytest.raises(send.NotAllowed, match="Gmail"):
        send.send_outreach(db, o["id"], dry_run=False)


def test_followup_draft_after_due(db, offline):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    o = db.insert("outreach", {"job_id": db.job_id, "contact_id": db.contact["id"], "kind": "cold", "status": "sent",
                               "to_email": "priya@acme.dev", "subject": "NetGuard → Intern", "body": "b",
                               "gmail_thread_id": "dryrun-1", "followup_due": past})
    assert followup.run(db)["followup_drafts"] == 1
    f = db.one("select * from outreach where parent_id = ?", (o["id"],))
    assert f["kind"] == "followup" and f["status"] == "draft" and f["subject"].startswith("Re: ")
    assert f["body"].startswith("Hi Priya,")
    assert followup.run(db)["followup_drafts"] == 0     # only one follow-up, ever
    assert any("follow-up" in t for t in offline)


def test_task_queue_prepare_and_failures(db, monkeypatch):
    monkeypatch.setattr("worker.outreach.contacts.find_domain", lambda db, c, u="": None)
    tid = db.enqueue("prepare", db.job_id)
    assert tasks.run_pending(db) == 4                    # prepare → tailor, find_contacts, draft_outreach
    kinds = {r["kind"]: r["status"] for r in db.query("select kind, status from tasks")}
    assert kinds == {"prepare": "done", "tailor": "done", "find_contacts": "done", "draft_outreach": "done"}
    assert db.get("matches", db.job_id, key="job_id")["status"] == "tailored"
    assert db.one("select count(*) n from outreach where status = 'draft'")["n"] >= 1
    bad = db.enqueue("send_outreach", db.job_id, {"outreach_id": "nope"})
    tasks.run_pending(db)
    t = db.get("tasks", bad)
    assert t["status"] == "failed" and "unknown outreach" in t["error"]
    assert tid


def test_telegram_buttons(db, monkeypatch):
    monkeypatch.setattr("worker.outreach.contacts.find_domain", lambda db, c, u="": None)
    assert "Skipped" in telegram_bot.handle_callback(db, f"sk:{db.job_id}")
    assert db.get("matches", db.job_id, key="job_id")["status"] == "skipped"
    assert "Shortlisted" in telegram_bot.handle_callback(db, f"sl:{db.job_id}")
    assert db.one("select count(*) n from tasks where status = 'queued'")["n"] == 3
    assert "Job not found" == telegram_bot.handle_callback(db, "sl:doesnotexist")
    assert "shortlisted" in telegram_bot.handle_command(db, "/status")


def test_tasks_run_in_queue_order_within_one_second(db, monkeypatch):
    order = []
    monkeypatch.setitem(tasks.HANDLERS, "prep", "worker.docs:run_task")
    monkeypatch.setattr("worker.docs.run_task", lambda d, t: order.append(t["payload"]["n"]) or {})
    for n in range(12):
        db.enqueue("prep", db.job_id, {"n": n})
    tasks.run_pending(db)
    assert order == list(range(12))
