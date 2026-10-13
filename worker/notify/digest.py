"""Daily digest (21:00) and weekly review (Sundays), sent to Telegram. The weekly report is also saved as a document."""
import html
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from ..config import DASHBOARD_URL, SETTINGS
from ..db import DB, now
from . import telegram

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _since(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def skill_gaps(db: DB, top_n: int = 50) -> list[tuple[str, int]]:
    """Skills most often missing across your best matches: what to learn next."""
    rows = db.query("select missing_skills from matches order by score desc limit ?", (top_n,))
    c = Counter(s for r in rows for s in json.loads(r["missing_skills"] or "[]"))
    return c.most_common(8)


def daily_text(db: DB) -> str:
    day = _since(1)
    new = db.one("select count(*) n from jobs where first_seen >= ?", (day,))["n"]
    top = db.query("select j.title, j.company, m.score from matches m join jobs j on j.id = m.job_id"
                   " where j.first_seen >= ? and m.status = 'new' order by m.score desc limit 5", (day,))
    drafts = db.one("select count(*) n from outreach where status = 'draft'")["n"]
    sent = db.one("select count(*) n from outreach where sent_at >= ?", (day,))["n"]
    replies = db.one("select count(*) n from outreach where status = 'replied' and updated_at >= ?", (day,))["n"]
    soon = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    deadlines = db.query("select j.title, j.company, m.deadline from matches m join jobs j on j.id = m.job_id"
                         " where m.deadline is not null and m.deadline >= ? and m.deadline <= ?"
                         " and m.status not in ('skipped', 'rejected') order by m.deadline limit 5", (now(), soon))
    lines = [f"<b>🌙 Daily digest</b>", f"New postings today: {new}"]
    if top:
        lines.append("Top new matches:")
        lines += [f"  {r['score']} · {html.escape(r['title'])} @ {html.escape(r['company'])}" for r in top]
    lines.append(f"Emails sent: {sent} · replies: {replies} · drafts waiting: {drafts}")
    if deadlines:
        lines.append("Deadlines this week:")
        lines += [f"  {r['deadline'][:10]} · {html.escape(r['title'])} @ {html.escape(r['company'])}" for r in deadlines]
    if DASHBOARD_URL:
        lines.append(DASHBOARD_URL)
    return "\n".join(lines)


def weekly_text(db: DB) -> str:
    week = _since(7)
    by_status = {r["status"]: r["n"] for r in db.query(
        "select status, count(*) n from matches where updated_at >= ? group by status", (week,))}
    sent = db.query("select variant, project_pitched, status from outreach where sent_at >= ? and kind = 'cold'", (week,))
    replied = [o for o in sent if o["status"] == "replied"]
    rate = f"{100 * len(replied) / len(sent):.0f}%" if sent else "n/a"
    by_variant = Counter(o["variant"] for o in replied)
    sources = db.query("select j.source, count(*) n from jobs j join matches m on m.job_id = j.id"
                       " where m.status in ('applied','oa','interview','offer') group by j.source order by n desc limit 5")
    gaps = skill_gaps(db)
    lines = ["<b>📊 Weekly review</b>",
             f"Applied: {by_status.get('applied', 0)} · OA: {by_status.get('oa', 0)} · interviews: "
             f"{by_status.get('interview', 0)} · offers: {by_status.get('offer', 0)} · rejected: {by_status.get('rejected', 0)}",
             f"Cold emails: {len(sent)} sent, reply rate {rate}"
             + (f" (replies by template: {dict(by_variant)})" if by_variant else "")]
    if sources:
        lines.append("Sources that led to applications: " + ", ".join(f"{html.escape(s['source'])} ({s['n']})" for s in sources))
    if gaps:
        lines.append("Skills to learn next (missing in your top matches): " + ", ".join(f"{s} ×{n}" for s, n in gaps[:6]))
    return "\n".join(lines)


def maybe_send(db: DB, at: datetime | None = None) -> list[str]:
    """Called every loop; sends each report at most once per day/week."""
    at = at or datetime.now()
    sent = []
    if at.hour >= SETTINGS["digest"]["hour"] and db.kv_get("digest_last") != at.date().isoformat():
        telegram.send(daily_text(db))
        db.kv_set("digest_last", at.date().isoformat())
        sent.append("daily")
    week_key = f"{at.isocalendar().year}-W{at.isocalendar().week}"
    if (WEEKDAYS[at.weekday()] == SETTINGS["digest"]["weekly_day"] and at.hour >= SETTINGS["digest"]["hour"]
            and db.kv_get("weekly_last") != week_key):
        text = weekly_text(db)
        telegram.send(text)
        db.insert("documents", {"kind": "weekly_report", "title": f"Weekly review {week_key}",
                                "content": text.replace("<b>", "**").replace("</b>", "**"), "created_at": now()})
        db.kv_set("weekly_last", week_key)
        sent.append("weekly")
    return sent
