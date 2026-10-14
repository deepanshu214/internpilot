"""The always-on worker (launchd keeps it running on your Mac):
- runs tasks queued by the dashboard / Telegram (tailor, contacts, drafts, send, autofill, docs)
- answers Telegram buttons and commands
- discovers new jobs every few hours, checks Gmail for application updates, creates follow-up drafts
- sends the daily digest and weekly review
Run in the foreground with: .venv/bin/python -m worker.agent"""
import argparse
import logging
import time
from datetime import datetime, timezone

from . import gmail, llm, tasks
from .db import DB, now
from .notify import digest, telegram_bot
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


def safely(name: str, fn, *args):
    try:
        return fn(*args)
    except Exception:
        log.exception("%s failed", name)


def tick(db: DB, discover_hours: float = 3) -> None:
    db.kv_set("worker_heartbeat", now())
    tasks.run_pending(db)
    safely("telegram", telegram_bot.poll, db)
    if due(db, "discover", discover_hours * 3600):
        log.info("discover: %s", safely("discover", run_once, db))
    if gmail.available() and due(db, "inbox", 30 * 60):
        log.info("inbox: %s", safely("inbox", inbox.run, db))
    if due(db, "followups", 6 * 3600):
        safely("followups", followup.run, db)
    safely("digest", digest.maybe_send, db)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover-hours", type=float, default=3)
    ap.add_argument("--interval", type=float, default=10, help="seconds between queue checks")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("JobSpy").setLevel(logging.WARNING)
    db = DB()
    llm.use_db(db)  # persist free-tier usage so caps hold across restarts and show in the dashboard
    log.info("worker started (gmail: %s, llm: %s)", gmail.available(), llm.chain("write") or "none")
    while True:
        safely("tick", tick, db, args.discover_hours)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
