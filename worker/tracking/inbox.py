"""Read your inbox (read-only) and move jobs along the pipeline: applied → oa → interview → offer / rejected.
Also marks outreach as replied when someone answers your cold email."""
import html
import logging
import re
from datetime import datetime, timedelta

from .. import gmail, llm
from ..config import SETTINGS
from ..db import DB, now
from ..notify import telegram
from ..outreach.company import norm_company

log = logging.getLogger(__name__)
STAGES = ["new", "shortlisted", "tailored", "applied", "oa", "interview", "offer"]
TERMINAL = {"rejected", "offer", "skipped"}

RULES = [  # (kind, pattern on subject+body); first match wins, order matters
    ("offer", r"\b(offer letter|pleased to offer|extend (you )?an offer|offer of (internship|employment))\b"),
    ("rejection", r"\b(unfortunately|regret to inform|not (be )?(moving|proceeding) forward|decided to (move|go) forward with other"
                  r"|will not be moving|position has been filled|not selected|other candidates)\b"),
    ("interview", r"\b(interview (invitation|invite|schedule)|schedule (an|your|a) (interview|call)|invite you to (an )?interview"
                  r"|next round|technical interview|calendly\.com|book a (time|slot))\b"),
    ("oa", r"\b(online assessment|coding (assessment|test|challenge)|hackerrank|codility|hackerearth|codesignal|mettl"
           r"|take[- ]home|assessment link|complete the (test|assessment))\b"),
    ("applied", r"\b(thank(s| you) for (applying|your application|your interest)|application (has been )?(received|submitted)"
                r"|we('ve| have) received your application|successfully applied)\b"),
]
ATS_SENDERS = re.compile(r"greenhouse|lever\.co|ashby|workday|myworkday|smartrecruiters|icims|taleo|successfactors"
                         r"|internshala|unstop|naukri|wellfound|hire|talent|recruit|careers|jobs", re.I)
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"


def classify(msg: dict) -> str:
    text = f"{msg['subject']}\n{msg['text'] or re.sub(r'<[^>]+>', ' ', msg['html'] or '')}"[:6000].lower()
    for kind, pattern in RULES:
        if re.search(pattern, text, re.I):
            return kind
    if llm.available("score") and ATS_SENDERS.search(msg["from"]):
        out = llm.chat_json('Classify this email about a job application. Return {"kind": one of "applied", "oa", '
                            '"interview", "rejection", "offer", "other"}', text[:3000], purpose="score")
        if out and out.get("kind") in {"applied", "oa", "interview", "rejection", "offer"}:
            return out["kind"]
    return "other"


def find_deadline(text: str, ref: datetime | None = None) -> str | None:
    """'complete by October 20' / 'by 20 Oct' / 'within 72 hours' → ISO date."""
    ref = ref or datetime.now()
    m = re.search(rf"\b(?:by|before|deadline:?|due:?)\s+(?:\w+day,?\s+)?(({MONTHS})[a-z]*\.?\s+(\d{{1,2}})|(\d{{1,2}})\s+({MONTHS})[a-z]*)",
                  text, re.I)
    if m:
        month = (m.group(2) or m.group(5)).lower()[:3]
        day = int(m.group(3) or m.group(4))
        mon = MONTHS.split("|").index(month) + 1
        year = ref.year + (1 if mon < ref.month - 6 else 0)
        try:
            return datetime(year, mon, day).date().isoformat()
        except ValueError:
            return None
    m = re.search(r"within\s+(\d{1,3})\s*(hours|hrs|days)", text, re.I)
    if m:
        n = int(m.group(1))
        return (ref + (timedelta(hours=n) if m.group(2).lower().startswith("h") else timedelta(days=n))).date().isoformat()
    return None


def match_job(db: DB, msg: dict) -> dict | None:
    """The job this email is about: same company name in sender/subject/body, furthest along the pipeline."""
    hay = norm_company(f"{msg['from']} {msg['subject']} {msg['text'][:3000] if msg['text'] else ''}")
    candidates = db.query("select j.id, j.company, j.title, m.status from jobs j join matches m on m.job_id = j.id"
                          " where m.status not in ('new', 'skipped')")
    hits = []
    for c in candidates:
        name = norm_company(c["company"])
        if len(name) >= 3 and re.search(rf"\b{re.escape(name)}\b", hay):
            title_hit = norm_company(c["title"]) in hay
            hits.append((title_hit, STAGES.index(c["status"]) if c["status"] in STAGES else 0, c))
    return max(hits, key=lambda h: (h[0], h[1]))[2] if hits else None


def apply_update(db: DB, job: dict, kind: str, msg: dict) -> str | None:
    target = {"applied": "applied", "oa": "oa", "interview": "interview", "rejection": "rejected", "offer": "offer"}[kind]
    current = job["status"]
    if current in TERMINAL and target != "offer":
        return None
    if target in STAGES and current in STAGES and STAGES.index(target) <= STAGES.index(current):
        return None  # never move backwards (a late "thanks for applying" after an OA invite)
    extra = {}
    if target == "applied":
        extra["applied_at"] = now()
    if target == "oa" and (deadline := find_deadline(f"{msg['subject']} {msg['text']}")):
        extra["deadline"] = deadline
    db.set_status(job["id"], target, **extra)
    return target


EMOJI = {"applied": "📨", "oa": "🧪", "interview": "🎤", "rejected": "🫡", "offer": "🎉"}


def run(db: DB) -> dict:
    if not gmail.available():
        return {"skipped": "gmail not authorized"}
    days = SETTINGS["tracking"]["gmail_query_days"]
    seen = set(db.kv_get("gmail_seen", []))
    ids = [i for i in gmail.search(f"newer_than:{days}d -from:me -category:promotions", 200) if i not in seen]
    threads = {o["gmail_thread_id"]: o for o in db.query(
        "select id, gmail_thread_id, job_id from outreach where status = 'sent' and gmail_thread_id is not null")}
    updates = []
    for mid in ids:
        msg = gmail.get(mid)
        seen.add(mid)
        if o := threads.get(msg["threadId"]):
            db.update("outreach", o["id"], {"status": "replied", "updated_at": now()})
            telegram.send(f"💬 Reply to your cold email: <b>{html.escape(msg['subject'])}</b>\n{html.escape(msg['snippet'][:200])}")
            updates.append({"outreach_replied": o["id"]})
            continue
        kind = classify(msg)
        if kind == "other":
            continue
        job = match_job(db, msg)
        if not job:
            continue
        moved = apply_update(db, job, kind, msg)
        if moved:
            telegram.send(f"{EMOJI[moved]} {html.escape(job['title'])} @ {html.escape(job['company'])} → <b>{moved}</b>\n"
                          f"{html.escape(msg['subject'])}")
            updates.append({"job": job["id"], "status": moved})
    db.kv_set("gmail_seen", list(seen)[-3000:])
    return {"checked": len(ids), "updates": updates}

