"""Send approved outreach through Gmail (or write .eml files while DRY_RUN=1). Drafts are never sent."""
from datetime import datetime, timedelta, timezone

from .. import gmail
from ..config import DRY_RUN, SETTINGS
from ..db import DB, now
from ..tailor.service import resume_attachment


class NotAllowed(Exception):
    pass


def sent_today(db: DB) -> int:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return db.one("select count(*) n from outreach where status in ('sent', 'replied') and sent_at >= ?",
                  (start.isoformat(timespec="seconds"),))["n"]


def send_outreach(db: DB, outreach_id: str, dry_run: bool = DRY_RUN) -> dict:
    o = db.get("outreach", outreach_id)
    if not o:
        raise ValueError(f"unknown outreach {outreach_id}")
    if o["status"] != "approved":
        raise NotAllowed(f"outreach is '{o['status']}', only 'approved' emails are sent")
    if not o.get("to_email"):
        raise NotAllowed("no recipient email: add a contact first")
    cap = SETTINGS["outreach"]["daily_cap"]
    if sent_today(db) >= cap:
        raise NotAllowed(f"daily cap of {cap} emails reached; it will go out tomorrow")
    if not dry_run and not gmail.available():
        raise NotAllowed("Gmail isn't authorized yet (run scripts/gmail_auth.py)")

    attachments = []
    if o["kind"] in ("cold", "referral") and o.get("job_id"):
        name, data = resume_attachment(db, o["job_id"])
        attachments.append((name, data, "application/pdf"))
    parent = db.get("outreach", o["parent_id"]) if o.get("parent_id") else None
    result = gmail.send(o["to_email"], o["subject"], o["body"], attachments,
                        thread_id=parent and parent.get("gmail_thread_id"),
                        in_reply_to=parent and parent.get("gmail_message_id"), dry_run=dry_run)

    followup = None
    if o["kind"] == "cold":
        days = SETTINGS["outreach"]["followup_days"]
        followup = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    db.update("outreach", outreach_id, {"status": "sent", "sent_at": now(), "updated_at": now(),
                                        "gmail_message_id": result["id"], "gmail_thread_id": result.get("threadId"),
                                        "followup_due": followup})
    db.log("sent" if not result["dry_run"] else "sent-dry-run", f"to {o['to_email']}: {o['subject']}", o.get("job_id"))
    return {"outreach_id": outreach_id, "dry_run": result["dry_run"], "path": result.get("path")}


def run_task(db: DB, task: dict) -> dict:
    return send_outreach(db, task["payload"]["outreach_id"])
