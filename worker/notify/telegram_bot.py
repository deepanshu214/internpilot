"""Two-way Telegram: handles the Shortlist / Skip buttons on alerts and a few commands.
Only messages from TELEGRAM_CHAT_ID (you) are acted on."""
import html
import json
import logging

import requests

from ..config import DASHBOARD_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from ..db import DB
from ..logsafe import redact
from . import telegram

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
HELP = ("Commands:\n/top: best new matches\n/status: pipeline counts\n/drafts: emails waiting for approval\n"
        "Buttons on alerts: ✅ Shortlist prepares resume + contacts + email drafts; ⏭ Skip hides the job.")


def _api(method: str, **params):
    r = requests.post(API.format(token=TELEGRAM_BOT_TOKEN, method=method), data=params, timeout=35)
    r.raise_for_status()
    return r.json().get("result")


def handle_callback(db: DB, data: str) -> str:
    from ..tasks import prepare

    action, _, job_id = data.partition(":")
    job = db.get("jobs", job_id)
    if not job:
        return "Job not found"
    if action == "sl":
        prepare(db, job_id)
        return f"Shortlisted. Preparing resume, contacts and drafts for {job['company']}…"
    if action == "sk":
        db.set_status(job_id, "skipped")
        return "Skipped"
    if action == "ap":
        db.enqueue("autofill", job_id)
        return "Opening the application on your Mac (you press Submit)"
    return "Unknown action"


def handle_command(db: DB, text: str) -> str:
    cmd = text.strip().split()[0].lower().split("@")[0]
    if cmd == "/top":
        rows = db.query("select j.id, j.title, j.company, m.score from matches m join jobs j on j.id = m.job_id"
                        " where m.status = 'new' order by m.score desc limit 5")
        return "\n".join(f"{r['score']} · {r['title']} @ {r['company']}" for r in rows) or "No new matches."
    if cmd == "/status":
        rows = db.query("select status, count(*) n from matches group by status order by n desc")
        return "\n".join(f"{r['status']}: {r['n']}" for r in rows) or "Empty."
    if cmd == "/drafts":
        n = db.one("select count(*) n from outreach where status = 'draft'")["n"]
        return f"{n} email draft(s) waiting." + (f"\n{DASHBOARD_URL}/outreach" if DASHBOARD_URL else "")
    return HELP


def poll(db: DB) -> int:
    """Process pending updates once (non-blocking). Returns how many were handled."""
    if not telegram.enabled():
        return 0
    offset = db.kv_get("telegram_offset", 0)
    try:
        updates = _api("getUpdates", offset=offset, timeout=0, allowed_updates=json.dumps(["message", "callback_query"]))
    except requests.RequestException as e:
        log.warning("telegram poll failed: %s", redact(str(e)))
        return 0
    handled = 0
    for u in updates or []:
        db.kv_set("telegram_offset", u["update_id"] + 1)
        if cb := u.get("callback_query"):
            if str(cb["message"]["chat"]["id"]) != str(TELEGRAM_CHAT_ID):
                continue
            reply = handle_callback(db, cb.get("data", ""))
            _api("answerCallbackQuery", callback_query_id=cb["id"], text=reply[:190])
            _api("editMessageReplyMarkup", chat_id=TELEGRAM_CHAT_ID, message_id=cb["message"]["message_id"],
                 reply_markup=json.dumps({"inline_keyboard": [[{"text": html.unescape(reply[:60]), "callback_data": "noop:"}]]}))
            handled += 1
        elif (msg := u.get("message")) and str(msg["chat"]["id"]) == str(TELEGRAM_CHAT_ID) and msg.get("text"):
            telegram.send(html.escape(handle_command(db, msg["text"])))
            handled += 1
    return handled
