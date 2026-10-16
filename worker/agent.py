"""The always-on worker (launchd keeps it running on your Mac):
- runs tasks queued by the dashboard / Telegram (tailor, contacts, drafts, send, autofill, docs)
- answers Telegram buttons and commands
- discovers new jobs every few hours, checks Gmail for application updates, creates follow-up drafts
- sends the daily digest and weekly review
Run in the foreground with: .venv/bin/python -m worker.agent"""
import argparse
import html
import logging
import time
from datetime import datetime, timezone

from . import gmail, llm, logsafe, tasks
from .config import ROOT, SETTINGS
from .db import DB, now
from .notify import digest, telegram, telegram_bot
from .outreach import followup
from .pipeline import run_once
from .tracking import inbox

log = logging.getLogger("worker.agent")


def due(db: DB, name: str, every_seconds: float) -> bool:
    last = db.kv_get(f"last:{name}")
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < every_seconds:
        return False
    db.kv_set(f"last:{name}", now())
    return True


def gmail_watch(db: DB):
    """Telegram heads-up the day before Google's 7-day Testing-mode login expiry, and once a day if it has expired."""
    if not gmail.GMAIL_TOKEN.exists():
        return
    today = datetime.now().date().isoformat()
    if gmail.expired():
        if db.kv_get("gmail_expired_notice") != today:
            db.kv_set("gmail_expired_notice", today)
            telegram.send("📧 <b>Gmail login expired</b> (Google does this every 7 days while your Google app is in "
                          "Testing). Inbox tracking and sending are paused. Reconnect in 30 s on your Mac:\n"
                          f"<code>{html.escape(gmail.REAUTH)}</code>")
        return
    if not SETTINGS["tracking"].get("gmail_app_in_testing", True):
        return
    mtime = gmail.GMAIL_TOKEN.stat().st_mtime
    if (time.time() - mtime) / 86400 >= 6 and db.kv_get("gmail_expiry_reminder") != int(mtime):
        db.kv_set("gmail_expiry_reminder", int(mtime))
        telegram.send("📧 Heads-up: your Gmail login for InternPilot expires in about a day (Google's 7-day limit for "
                      "apps in Testing). Reconnect on your Mac when convenient:\n"
                      f"<code>{html.escape(gmail.REAUTH)}</code>")


def offline(e: BaseException) -> bool:
    """Network outage (Mac asleep / Wi-Fi down): worth one log line, not a traceback."""
    import requests
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError)) or \
                "NameResolution" in type(e).__name__ or "nodename nor servname" in str(e):
            return True
        e = e.__cause__ or e.__context__
    return False


def safely(name: str, fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        if offline(e):
            log.warning("%s skipped: network unavailable", name)
        else:
            log.exception("%s failed", name)


def tick(db: DB, discover_hours: float = 3) -> None:
    db.kv_set("worker_heartbeat", now())
    tasks.run_pending(db)
    safely("telegram", telegram_bot.poll, db)
    if due(db, "discover", discover_hours * 3600):
        log.info("discover: %s", safely("discover", run_once, db))
    if gmail.available() and due(db, "inbox", 30 * 60):
        try:
            log.info("inbox: %s", inbox.run(db))
        except gmail.AuthExpired:
            log.warning("gmail login expired")
        except Exception as e:
            if offline(e):
                log.warning("inbox skipped: network unavailable")
            else:
                log.exception("inbox failed")
    safely("gmail-watch", gmail_watch, db)
    if due(db, "followups", 6 * 3600):
        safely("followups", followup.run, db)
    safely("digest", digest.maybe_send, db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover-hours", type=float, default=3)
    ap.add_argument("--interval", type=float, default=10, help="seconds between queue checks")
    args = ap.parse_args()
    logsafe.setup(ROOT / "logs" / "worker.log")
    db = DB()
    llm.use_db(db)  # persist free-tier usage so caps hold across restarts and show in the dashboard
    log.info("worker started (gmail: %s, llm: %s)", gmail.available(), llm.chain("write") or "none")
    while True:
        safely("tick", tick, db, args.discover_hours)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
